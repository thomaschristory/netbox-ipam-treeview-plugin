from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from ipam.models import Prefix
from users.models import ObjectPermission

from netbox_ipam_treeview.tree.builder import NodeNotFound, TreeBuilder
from netbox_ipam_treeview.tree.nodes import agg_key, pfx_key, vrf_key

from .fixtures import make_tree, superuser


def kinds(nodes):
    return [(n.kind, str(n.network) if n.network is not None else (n.obj.name if n.obj else "Global")) for n in nodes]


class RootsTest(TestCase):
    def setUp(self):
        self.t = make_tree()
        self.user = superuser()

    def test_roots_grouped_by_vrf_global_first(self):
        roots = TreeBuilder(self.user).roots()
        self.assertEqual([n.key for n in roots], [vrf_key(None), vrf_key(self.t["red"].pk)])
        self.assertTrue(all(n.level == 0 and n.has_children for n in roots))

    def test_vrf_children_aggregate_then_orphan(self):
        nodes = TreeBuilder(self.user, show_free_space=False).children(vrf_key(None), 0)
        self.assertEqual(kinds(nodes), [("aggregate", "10.0.0.0/8"), ("prefix", "192.0.2.0/24")])
        self.assertEqual(nodes[0].key, agg_key(self.t["agg"].pk, None))
        self.assertEqual(nodes[0].level, 1)

    def test_aggregate_appears_in_red_vrf_with_only_red_prefixes(self):
        b = TreeBuilder(self.user, show_free_space=False)
        red_children = b.children(vrf_key(self.t["red"].pk), 0)
        self.assertEqual(kinds(red_children), [("aggregate", "10.0.0.0/8")])
        under = b.children(red_children[0].key, 1)
        self.assertEqual([n.obj.pk for n in under], [self.t["r16"].pk])

    def test_prefix_children_one_level(self):
        nodes = TreeBuilder(self.user, show_free_space=False).children(pfx_key(self.t["p16"].pk), 2)
        self.assertEqual([n.obj.pk for n in nodes], [self.t["p24"].pk])
        self.assertTrue(nodes[0].has_children)
        self.assertEqual(nodes[0].level, 3)

    def test_gaps_interleaved(self):
        nodes = TreeBuilder(self.user).children(pfx_key(self.t["p24"].pk), 0)
        self.assertEqual(kinds(nodes), [("prefix", "10.1.1.0/26"), ("gap", "10.1.1.64/26"), ("gap", "10.1.1.128/25")])

    def test_no_gaps_under_mark_utilized(self):
        Prefix.objects.filter(pk=self.t["p24"].pk).update(mark_utilized=True)
        nodes = TreeBuilder(self.user).children(pfx_key(self.t["p24"].pk), 0)
        self.assertEqual([n.kind for n in nodes], ["prefix"])

    def test_ipv6_sparse_parent_gap_cap(self):
        p = Prefix.objects.create(prefix="fd00::/32", status="container")
        Prefix.objects.create(prefix="fd00:0:ffff::/64")
        nodes = TreeBuilder(self.user, max_gap_rows=5).children(pfx_key(p.pk), 0)
        self.assertEqual(sum(n.kind == "gap" for n in nodes), 5)
        self.assertEqual(nodes[-1].kind, "more")

    def test_ungrouped_roots(self):
        roots = TreeBuilder(self.user, group_by_vrf=False).roots()
        self.assertEqual(kinds(roots), [("aggregate", "10.0.0.0/8"), ("prefix", "192.0.2.0/24")])

    def test_unknown_key_raises(self):
        with self.assertRaises(NodeNotFound):
            TreeBuilder(self.user).children(pfx_key(999999), 0)

    def test_malformed_key_raises(self):
        with self.assertRaises(NodeNotFound):
            TreeBuilder(self.user).children("garbage", 0)


class PermissionTest(TestCase):
    def setUp(self):
        self.t = make_tree()
        self.user = get_user_model().objects.create_user("limited")
        perm = ObjectPermission.objects.create(
            name="view some prefixes", actions=["view"], constraints={"prefix__net_contained_or_equal": "10.1.1.0/24"}
        )
        perm.object_types.add(ContentType.objects.get_for_model(Prefix))
        perm.users.add(self.user)

    def test_no_aggregate_perm_skips_aggregate_level(self):
        nodes = TreeBuilder(self.user, show_free_space=False).children(vrf_key(None), 0)
        self.assertEqual(kinds(nodes), [("prefix", "10.1.1.0/24")])

    def test_restricted_user_sees_grandchild_through_hidden_parent(self):
        # 10.1.0.0/16 is hidden, so 10.1.1.0/24 is the visible root; its /26 child must appear under it.
        b = TreeBuilder(self.user, show_free_space=False)
        root = b.children(vrf_key(None), 0)[0]
        self.assertEqual([n.obj.pk for n in b.children(root.key, 1)], [self.t["p26"].pk])

    def test_hidden_prefix_key_not_found(self):
        with self.assertRaises(NodeNotFound):
            TreeBuilder(self.user).children(pfx_key(self.t["p16"].pk), 0)

    def test_restricted_user_gets_no_free_space(self):
        # Hidden prefixes would otherwise be presented as free space.
        nodes = TreeBuilder(self.user, show_free_space=True).children(pfx_key(self.t["p24"].pk), 0)
        self.assertEqual([n.kind for n in nodes], ["prefix"])

    def test_restricted_user_child_count_hidden(self):
        root = TreeBuilder(self.user).children(vrf_key(None), 0)[0]
        self.assertIsNone(root.child_count)


class HiddenChildrenTest(TestCase):
    def setUp(self):
        self.t = make_tree()
        self.user = get_user_model().objects.create_user("containers-only")
        perm = ObjectPermission.objects.create(name="containers", actions=["view"], constraints={"status": "container"})
        perm.object_types.add(ContentType.objects.get_for_model(Prefix))
        perm.users.add(self.user)

    def test_no_toggle_when_all_children_hidden(self):
        nodes = TreeBuilder(self.user).children(vrf_key(None), 0)
        self.assertEqual(kinds(nodes), [("prefix", "10.1.0.0/16")])
        self.assertFalse(nodes[0].has_children)

    def test_hidden_vrf_not_listed(self):
        # The user may see RED's container prefix but not the RED VRF itself.
        self.assertEqual([n.key for n in TreeBuilder(self.user).roots()], [vrf_key(None)])
        nodes = TreeBuilder(self.user).filtered(Prefix.objects.filter(pk=self.t["r16"].pk))
        self.assertEqual(nodes, [])

    def test_unrestricted_child_count(self):
        root = TreeBuilder(superuser(), show_free_space=False).children(pfx_key(self.t["p16"].pk), 0)[0]
        self.assertEqual(root.child_count, 1)
