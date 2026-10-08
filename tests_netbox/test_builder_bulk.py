from django.test import TestCase
from ipam.models import Prefix

from netbox_ipam_treeview.tree.builder import TreeBuilder
from netbox_ipam_treeview.tree.nodes import pfx_key, vrf_key

from .fixtures import make_tree, superuser


class SubtreeTest(TestCase):
    def setUp(self):
        self.t = make_tree()
        self.user = superuser()

    def test_subtree_of_prefix(self):
        nodes = TreeBuilder(self.user, show_free_space=False).subtree(pfx_key(self.t["p16"].pk), 0)
        self.assertEqual([(n.obj.pk, n.level) for n in nodes], [(self.t["p24"].pk, 1), (self.t["p26"].pk, 2)])
        self.assertTrue(nodes[0].expanded)
        self.assertEqual(nodes[1].parent_key, pfx_key(self.t["p24"].pk))

    def test_subtree_of_global_vrf(self):
        nodes = TreeBuilder(self.user, show_free_space=False).subtree(vrf_key(None), 0)
        self.assertEqual(
            [(n.kind, str(n.network), n.level) for n in nodes],
            [
                ("aggregate", "10.0.0.0/8", 1),
                ("prefix", "10.1.0.0/16", 2),
                ("prefix", "10.1.1.0/24", 3),
                ("prefix", "10.1.1.0/26", 4),
                ("prefix", "192.0.2.0/24", 1),
            ],
        )

    def test_subtree_has_gaps(self):
        nodes = TreeBuilder(self.user).subtree(pfx_key(self.t["p24"].pk), 0)
        self.assertEqual([n.kind for n in nodes], ["prefix", "gap", "gap"])

    def test_subtree_truncates(self):
        b = TreeBuilder(self.user, limit=2)
        nodes = b.subtree(vrf_key(None), 0)
        self.assertTrue(b.truncated)
        self.assertLessEqual(sum(n.kind == "prefix" for n in nodes), 2)
        self.assertFalse(any(n.kind == "gap" for n in nodes))

    def test_full_tree(self):
        nodes = TreeBuilder(self.user, show_free_space=False).full_tree()
        self.assertEqual(nodes[0].key, vrf_key(None))
        self.assertTrue(nodes[0].expanded)
        self.assertIn(vrf_key(self.t["red"].pk), [n.key for n in nodes])
        self.assertEqual(sum(n.kind == "prefix" for n in nodes), 6)

    def test_expand_restores_state(self):
        keys = {vrf_key(None), pfx_key(self.t["orphan"].pk)}
        nodes = TreeBuilder(self.user, show_free_space=False).expand(keys)
        self.assertEqual([(n.kind, n.level) for n in nodes], [("vrf", 0), ("aggregate", 1), ("prefix", 1), ("vrf", 0)])
        self.assertTrue(nodes[0].expanded)
        self.assertFalse(nodes[1].expanded)

    def test_expand_ignores_unknown_keys(self):
        nodes = TreeBuilder(self.user).expand({"pfx:999999", "garbage"})
        self.assertEqual([n.kind for n in nodes], ["vrf", "vrf"])

    def test_filtered_shows_ancestors_as_context(self):
        nodes = TreeBuilder(self.user).filtered(Prefix.objects.filter(pk=self.t["p26"].pk))
        self.assertEqual(
            [(n.kind, str(n.network) if n.network is not None else None, n.context) for n in nodes],
            [
                ("vrf", None, True),
                ("aggregate", "10.0.0.0/8", True),
                ("prefix", "10.1.0.0/16", True),
                ("prefix", "10.1.1.0/24", True),
                ("prefix", "10.1.1.0/26", False),
            ],
        )
        self.assertTrue(all(n.expanded for n in nodes[:-1]))
        self.assertEqual([n.level for n in nodes], [0, 1, 2, 3, 4])

    def test_filtered_empty(self):
        self.assertEqual(TreeBuilder(self.user).filtered(Prefix.objects.none()), [])
