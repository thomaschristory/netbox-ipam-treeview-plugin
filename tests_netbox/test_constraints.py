"""Constrained object permissions: hidden prefixes, aggregates and VRFs must not appear through any endpoint."""

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from extras.models import Tag
from ipam.models import RIR, VRF, Aggregate, Prefix
from tenancy.models import Tenant
from users.models import Group, ObjectPermission
from utilities.testing import TestCase

from netbox_ipam_treeview.tree.builder import TreeBuilder
from netbox_ipam_treeview.tree.nodes import agg_key, pfx_key, tab_key, vrf_key

from .fixtures import make_tree

NS = "plugins:netbox_ipam_treeview:"
GAP_ROW = 'class="ipt-row ipt-gap'


def grant(model, constraints, *, users=(), groups=()):
    perm = ObjectPermission.objects.create(
        name=f"view {model._meta.model_name}", actions=["view"], constraints=constraints
    )
    perm.object_types.add(ContentType.objects.get_for_model(model))
    perm.users.add(*users)
    perm.groups.add(*groups)
    return perm


class ConstraintTestCase(TestCase):
    """Prefix view is constrained per test; aggregates and VRFs are visible unless a test says otherwise."""

    user_permissions = ("ipam.view_aggregate", "ipam.view_vrf")

    def setUp(self):
        super().setUp()
        self.t = make_tree()

    def get(self, name, **params):
        return self.client.get(reverse(NS + name), params)

    def every_endpoint(self):
        """Responses of each way the tree can be loaded, all keys known to exist expanded."""
        t = self.t
        keys = [vrf_key(None), vrf_key(t["red"].pk), agg_key(t["agg"].pk, None), agg_key(t["agg"].pk, t["red"].pk)]
        keys += [pfx_key(t[k].pk) for k in ("p16", "p24", "p26", "orphan", "r16", "r24")]
        responses = {
            "page": self.get("tree"),
            "expand_all": self.get("subtree", key="__root__"),
            "restore": self.get("expand", keys=",".join(keys)),
            "restore_all": self.get("expand", all="1"),
            "filtered": self.get("tree", family="4"),
            "ipv4_only": self.get("subtree", key="__root__", af="4"),
        }
        for key in keys[:4]:
            responses[f"children {key}"] = self.get("children", key=key, level="0")
            responses[f"subtree {key}"] = self.get("subtree", key=key, level="0")
        return responses

    def assertHidden(self, *names):
        for label, r in self.every_endpoint().items():
            self.assertIn(r.status_code, (200, 404), label)
            for name in names:
                self.assertNotContains(
                    r,
                    f'data-key="{pfx_key(self.t[name].pk)}"',
                    status_code=r.status_code,
                    msg_prefix=f"{label}: {name}",
                )

    def assertUnreachable(self, *names):
        """A hidden prefix cannot be opened directly, through its key or its Tree tab."""
        for name in names:
            pk = self.t[name].pk
            for endpoint in ("children", "subtree"):
                r = self.get(endpoint, key=pfx_key(pk), level="0")
                self.assertEqual(r.status_code, 404, f"{endpoint} {name}")
            self.assertEqual(self.get("expand", tab=tab_key("prefix", pk), all="1").status_code, 404, name)
            self.assertEqual(self.client.get(reverse("ipam:prefix_tree", kwargs={"pk": pk})).status_code, 404, name)


class VRFConstraintTest(ConstraintTestCase):
    def setUp(self):
        super().setUp()
        grant(Prefix, {"vrf__name": "RED"}, users=[self.user])

    def test_global_prefixes_hidden_everywhere(self):
        self.assertHidden("p16", "p24", "p26", "orphan")
        self.assertUnreachable("p16", "p24", "p26", "orphan")

    def test_red_prefixes_shown(self):
        r = self.get("subtree", key="__root__")
        self.assertContains(r, f'data-key="{pfx_key(self.t["r16"].pk)}"')
        self.assertContains(r, f'data-key="{pfx_key(self.t["r24"].pk)}"')

    def test_global_group_not_listed(self):
        r = self.get("tree")
        self.assertNotContains(r, f'data-key="{vrf_key(None)}"')
        self.assertContains(r, f'data-key="{vrf_key(self.t["red"].pk)}"')

    def test_aggregate_tab_lists_only_red(self):
        agg = self.t["agg"].pk
        r = self.client.get(reverse("ipam:aggregate_tree", kwargs={"pk": agg}))
        self.assertContains(r, f'data-key="{agg_key(agg, self.t["red"].pk)}"')
        self.assertNotContains(r, f'data-key="{agg_key(agg, None)}"')


class GlobalOnlyConstraintTest(ConstraintTestCase):
    def setUp(self):
        super().setUp()
        grant(Prefix, {"vrf__isnull": True}, users=[self.user])

    def test_vrf_prefixes_hidden_everywhere(self):
        self.assertHidden("r16", "r24")
        self.assertUnreachable("r16", "r24")

    def test_vrf_tab_shows_no_prefixes(self):
        r = self.client.get(reverse("ipam:vrf_tree", kwargs={"pk": self.t["red"].pk}))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, f'data-key="{pfx_key(self.t["r16"].pk)}"')
        self.assertNotContains(r, f'data-key="{pfx_key(self.t["r24"].pk)}"')


class TenantConstraintTest(ConstraintTestCase):
    """Only the middle of a chain is visible: its parent and child are hidden."""

    def setUp(self):
        super().setUp()
        tenant = Tenant.objects.create(name="Blue", slug="blue")
        Prefix.objects.filter(pk=self.t["p24"].pk).update(tenant=tenant)
        grant(Prefix, {"tenant__slug": "blue"}, users=[self.user])

    def test_only_tenant_prefix_shown(self):
        self.assertHidden("p16", "p26", "orphan", "r16", "r24")
        self.assertUnreachable("p16", "p26", "orphan", "r16", "r24")
        r = self.get("subtree", key="__root__")
        self.assertContains(r, f'data-key="{pfx_key(self.t["p24"].pk)}"')

    def test_no_toggle_free_space_or_child_count(self):
        b = TreeBuilder(self.user, show_free_space=True)
        self.assertTrue(b.restricted)
        [node] = [n for n in b.full_tree() if n.kind == "prefix"]
        self.assertEqual(node.obj.pk, self.t["p24"].pk)
        self.assertFalse(node.has_children)  # its /26 child is hidden
        self.assertIsNone(node.child_count)
        r = self.get("subtree", key="__root__")
        self.assertNotContains(r, GAP_ROW)


class TagConstraintTest(ConstraintTestCase):
    """Many-to-many constraints: a prefix matching several tags must still be one row and one object."""

    def setUp(self):
        super().setUp()
        a = Tag.objects.create(name="A", slug="a")
        b = Tag.objects.create(name="B", slug="b")
        for name in ("p16", "p24"):
            self.t[name].tags.add(a, b)
        grant(Prefix, [{"tags__slug": "a"}, {"tags__slug": "b"}], users=[self.user])

    def test_prefix_with_two_matching_tags_listed_once(self):
        for label, r in self.every_endpoint().items():
            self.assertIn(r.status_code, (200, 404), label)
            for name in ("p16", "p24"):
                key = f'data-key="{pfx_key(self.t[name].pk)}"'
                self.assertLessEqual(r.content.decode().count(key), 1, f"{label}: {name}")

    def test_tagged_prefix_opens(self):
        for endpoint in ("children", "subtree"):
            r = self.get(endpoint, key=pfx_key(self.t["p16"].pk), level="0")
            self.assertContains(r, f'data-key="{pfx_key(self.t["p24"].pk)}"', msg_prefix=endpoint)
        r = self.client.get(reverse("ipam:prefix_tree", kwargs={"pk": self.t["p16"].pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get("expand", tab=tab_key("prefix", self.t["p16"].pk), all="1").status_code, 200)

    def test_untagged_prefixes_hidden(self):
        self.assertHidden("p26", "orphan", "r16", "r24")
        self.assertUnreachable("p26", "orphan", "r16", "r24")


class CombinedPermissionsTest(ConstraintTestCase):
    """Separate permissions add up; a list of constraints in one permission is OR-ed the same way."""

    def test_two_permissions(self):
        grant(Prefix, {"vrf__name": "RED"}, users=[self.user])
        grant(Prefix, {"prefix": "192.0.2.0/24"}, users=[self.user])
        self.assert_red_and_orphan()

    def test_constraint_list(self):
        grant(Prefix, [{"vrf__name": "RED"}, {"prefix": "192.0.2.0/24"}], users=[self.user])
        self.assert_red_and_orphan()

    def test_group_permission(self):
        group = Group.objects.create(name="ipam readers")
        self.user.groups.add(group)
        grant(Prefix, [{"vrf__name": "RED"}, {"prefix": "192.0.2.0/24"}], groups=[group])
        self.assert_red_and_orphan()

    def test_unconstrained_permission_wins(self):
        grant(Prefix, {"vrf__name": "RED"}, users=[self.user])
        grant(Prefix, None, users=[self.user])
        self.assertFalse(TreeBuilder(self.user).restricted)
        r = self.get("subtree", key="__root__")
        for name in ("p16", "p24", "p26", "orphan", "r16", "r24"):
            self.assertContains(r, f'data-key="{pfx_key(self.t[name].pk)}"', msg_prefix=name)

    def assert_red_and_orphan(self):
        self.assertHidden("p16", "p24", "p26")
        self.assertUnreachable("p16", "p24", "p26")
        r = self.get("subtree", key="__root__")
        for name in ("orphan", "r16", "r24"):
            self.assertContains(r, f'data-key="{pfx_key(self.t[name].pk)}"', msg_prefix=name)


class AggregateConstraintTest(ConstraintTestCase):
    """A hidden aggregate drops out; its prefixes move up to the VRF level."""

    user_permissions = ("ipam.view_prefix", "ipam.view_vrf")

    def setUp(self):
        super().setUp()
        other = RIR.objects.create(name="Other", slug="other")
        self.visible = Aggregate.objects.create(prefix="198.51.100.0/24", rir=other)
        grant(Aggregate, {"rir__slug": "other"}, users=[self.user])

    def test_hidden_aggregate_not_listed(self):
        agg = self.t["agg"].pk
        for label, r in self.every_endpoint().items():
            for v in (None, self.t["red"].pk):
                self.assertNotContains(r, f'data-key="{agg_key(agg, v)}"', status_code=r.status_code, msg_prefix=label)

    def test_prefixes_under_vrf_directly(self):
        nodes = TreeBuilder(self.user, show_free_space=False).children(vrf_key(None), 0)
        self.assertEqual([n.obj.pk for n in nodes], [self.t["p16"].pk, self.t["orphan"].pk])

    def test_hidden_aggregate_unreachable(self):
        agg = self.t["agg"].pk
        for endpoint in ("children", "subtree"):
            self.assertEqual(self.get(endpoint, key=agg_key(agg, None), level="0").status_code, 404, endpoint)
        self.assertEqual(self.get("expand", tab=tab_key("aggregate", agg), all="1").status_code, 404)
        self.assertEqual(self.client.get(reverse("ipam:aggregate_tree", kwargs={"pk": agg})).status_code, 404)


class VRFObjectConstraintTest(ConstraintTestCase):
    """VRF view constrained to RED: another VRF and its group are unreachable even though its prefixes are not."""

    user_permissions = ("ipam.view_prefix", "ipam.view_aggregate")

    def setUp(self):
        super().setUp()
        self.blue = VRF.objects.create(name="BLUE")
        self.t["b24"] = Prefix.objects.create(prefix="10.7.0.0/24", vrf=self.blue)
        grant(VRF, {"name": "RED"}, users=[self.user])

    def test_hidden_vrf_group_not_listed(self):
        r = self.get("tree")
        self.assertContains(r, f'data-key="{vrf_key(self.t["red"].pk)}"')
        self.assertNotContains(r, f'data-key="{vrf_key(self.blue.pk)}"')
        self.assertNotContains(self.get("subtree", key="__root__"), f'data-key="{pfx_key(self.t["b24"].pk)}"')

    def test_hidden_vrf_unreachable(self):
        for endpoint in ("children", "subtree"):
            self.assertEqual(self.get(endpoint, key=vrf_key(self.blue.pk), level="0").status_code, 404, endpoint)
            r = self.get(endpoint, key=agg_key(self.t["agg"].pk, self.blue.pk), level="0")
            self.assertEqual(r.status_code, 404, f"{endpoint} aggregate@BLUE")
        self.assertEqual(self.get("expand", tab=tab_key("vrf", self.blue.pk), all="1").status_code, 404)
        self.assertEqual(self.client.get(reverse("ipam:vrf_tree", kwargs={"pk": self.blue.pk})).status_code, 404)
