from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from ipam.models import Aggregate, Prefix
from users.models import ObjectPermission
from utilities.testing import TestCase

from netbox_ipam_treeview.conf import FAMILY_COOKIE, family_preference
from netbox_ipam_treeview.tree.builder import NodeNotFound, TreeBuilder
from netbox_ipam_treeview.tree.nodes import agg_key, pfx_key, tab_key, vrf_key

from .fixtures import VIEW_PERMISSIONS, make_tree

NS = "plugins:netbox_ipam_treeview:"


def make_v6(t):
    """Adds to make_tree(): global agg 2001:db8::/32 > 2001:db8:1::/48 > 2001:db8:1::/64 ; VRF RED: 2001:db8:2::/48."""
    t["agg6"] = Aggregate.objects.create(prefix="2001:db8::/32", rir=t["agg"].rir)
    t["p48"] = Prefix.objects.create(prefix="2001:db8:1::/48", status="container")
    t["p64"] = Prefix.objects.create(prefix="2001:db8:1::/64")
    t["r48"] = Prefix.objects.create(prefix="2001:db8:2::/48", vrf=t["red"])
    for k in ("p48", "p64", "r48"):
        t[k].refresh_from_db()
    t["p16"].refresh_from_db()
    return t


def networks(nodes):
    return [str(n.network) for n in nodes if n.network is not None]


class FamilyPreferenceTest(TestCase):
    def test_query_wins_then_cookie(self):
        self.assertEqual(family_preference("6", "4"), 6)
        self.assertIsNone(family_preference("", "4"))  # ?af= (Both) overrides a remembered family
        self.assertEqual(family_preference(None, "4"), 4)
        self.assertIsNone(family_preference(None, None))
        for junk in ("5", "x", "46"):
            self.assertIsNone(family_preference(junk, None))
            self.assertIsNone(family_preference(None, junk))


class FamilyBuilderTest(TestCase):
    """The IPv4 / IPv6 selector restricts every level of the tree (#27)."""

    user_permissions = VIEW_PERMISSIONS

    def setUp(self):
        super().setUp()
        self.t = make_v6(make_tree())

    def test_both_by_default(self):
        nodes = TreeBuilder(self.user, show_free_space=False).children(vrf_key(None), 0)
        self.assertEqual(networks(nodes), ["10.0.0.0/8", "192.0.2.0/24", "2001:db8::/32"])

    def test_ipv6_hides_ipv4_aggregates_and_prefixes(self):
        b = TreeBuilder(self.user, show_free_space=False, family=6)
        self.assertEqual(networks(b.children(vrf_key(None), 0)), ["2001:db8::/32"])
        agg6 = agg_key(self.t["agg6"].pk, None)
        self.assertEqual(networks(b.children(agg6, 1)), ["2001:db8:1::/48"])
        self.assertEqual(networks(b.children(vrf_key(self.t["red"].pk), 0)), ["2001:db8::/32"])

    def test_ipv4_hides_ipv6(self):
        b = TreeBuilder(self.user, show_free_space=False, family=4)
        self.assertEqual(networks(b.children(vrf_key(None), 0)), ["10.0.0.0/8", "192.0.2.0/24"])

    def test_vrf_group_without_prefixes_of_the_family_is_hidden(self):
        self.t["r48"].delete()
        keys = [n.key for n in TreeBuilder(self.user, family=6).roots()]
        self.assertEqual(keys, [vrf_key(None)])

    def test_free_space_follows_family(self):
        nodes = TreeBuilder(self.user, show_free_space=True, family=6).children(vrf_key(None), 0)
        nodes = TreeBuilder(self.user, show_free_space=True, family=6).children(nodes[0].key, 1)
        gaps = [str(n.network) for n in nodes if n.kind == "gap"]
        self.assertTrue(gaps)
        self.assertTrue(all(":" in g for g in gaps))

    def test_full_tree_and_expand_follow_family(self):
        b = TreeBuilder(self.user, show_free_space=False, family=6)
        nets = networks(b.full_tree())
        self.assertIn("2001:db8:1::/64", nets)
        self.assertFalse([n for n in nets if "." in n])
        b = TreeBuilder(self.user, show_free_space=False, family=6)
        keys = [vrf_key(None), agg_key(self.t["agg6"].pk, None), agg_key(self.t["agg"].pk, None)]
        nets = networks(b.expand(keys))
        self.assertIn("2001:db8:1::/48", nets)
        self.assertFalse([n for n in nets if "." in n])

    def test_prefix_of_the_other_family_is_not_found(self):
        with self.assertRaises(NodeNotFound):
            TreeBuilder(self.user, family=6).children(pfx_key(self.t["p16"].pk), 1)

    def test_filtered_follows_family(self):
        nodes = TreeBuilder(self.user, family=6).filtered(Prefix.objects.filter(status="container"))
        nets = networks(nodes)
        self.assertIn("2001:db8:1::/48", nets)
        self.assertFalse([n for n in nets if "." in n])


class ConstrainedFamilyTest(TestCase):
    """Constrained users nest under their nearest visible ancestor: the family applies on that path too."""

    user_permissions = ("ipam.view_aggregate", "ipam.view_vrf")

    def setUp(self):
        super().setUp()
        self.t = make_v6(make_tree())
        perm = ObjectPermission.objects.create(name="active", actions=["view"], constraints={"status": "active"})
        perm.object_types.add(ContentType.objects.get_for_model(Prefix))
        perm.users.add(self.user)

    def test_family_on_nearest_visible_ancestor_path(self):
        b = TreeBuilder(self.user, family=6)
        self.assertTrue(b.restricted)
        nodes = b.children(vrf_key(None), 0)
        self.assertEqual(networks(nodes), ["2001:db8::/32"])
        # 2001:db8:1::/48 (a container) is hidden: its /64 hangs under the aggregate, with no free space.
        self.assertEqual(networks(b.children(nodes[0].key, 1)), ["2001:db8:1::/64"])
        b = TreeBuilder(self.user, family=4)
        self.assertEqual(networks(b.children(vrf_key(None), 0)), ["10.0.0.0/8", "192.0.2.0/24"])
        self.assertEqual(
            networks(b.full_tree()),
            ["10.0.0.0/8", "10.1.1.0/24", "10.1.1.0/26", "192.0.2.0/24", "10.0.0.0/8", "10.1.9.0/24"],
        )


class FamilyViewTest(TestCase):
    user_permissions = VIEW_PERMISSIONS

    def setUp(self):
        super().setUp()
        self.t = make_v6(make_tree())
        self.vrf0 = {"key": vrf_key(None), "level": "0", "free": "0"}

    def test_selector_on_page(self):
        r = self.client.get(reverse(NS + "tree"))
        self.assertContains(r, 'data-ipt-action="family"')
        self.assertContains(r, 'data-family=""')

    def test_page_parameter_does_not_switch_to_filtered_mode(self):
        r = self.client.get(reverse(NS + "tree"), {"af": "6"})
        self.assertContains(r, 'data-filtered="0"')
        self.assertContains(r, 'data-family="6"')

    def test_children_endpoint_follows_parameter(self):
        r = self.client.get(reverse(NS + "children"), {**self.vrf0, "af": "6"})
        self.assertContains(r, "2001:db8::/32")
        self.assertNotContains(r, "10.0.0.0/8")

    def test_remembered_family_applies(self):
        self.client.cookies[FAMILY_COOKIE] = "4"
        r = self.client.get(reverse(NS + "children"), self.vrf0)
        self.assertContains(r, "10.0.0.0/8")
        self.assertNotContains(r, "2001:db8::/32")
        self.assertContains(self.client.get(reverse(NS + "tree")), 'data-family="4"')

    def test_parameter_wins_over_cookie(self):
        self.client.cookies[FAMILY_COOKIE] = "4"
        r = self.client.get(reverse(NS + "children"), {**self.vrf0, "af": ""})
        self.assertContains(r, "10.0.0.0/8")
        self.assertContains(r, "2001:db8::/32")

    def test_subtree_and_expand_follow_parameter(self):
        r = self.client.get(reverse(NS + "subtree"), {"key": "__root__", "af": "6", "free": "0"})
        self.assertContains(r, "2001:db8:1::/64")
        self.assertNotContains(r, "10.1.1.0/26")
        keys = f"{vrf_key(None)},{agg_key(self.t['agg6'].pk, None)}"
        r = self.client.get(reverse(NS + "expand"), {"keys": keys, "af": "6", "free": "0"})
        self.assertContains(r, "2001:db8:1::/48")
        self.assertNotContains(r, "192.0.2.0/24")

    def test_filters_combine_with_family(self):
        r = self.client.get(reverse(NS + "tree"), {"status": "container", "af": "6"})
        self.assertContains(r, 'data-filtered="1"')
        self.assertContains(r, "2001:db8:1::/48")
        self.assertNotContains(r, "10.1.0.0/16")


class FamilyTabTest(TestCase):
    user_permissions = VIEW_PERMISSIONS

    def setUp(self):
        super().setUp()
        self.t = make_v6(make_tree())
        self.client.cookies[FAMILY_COOKIE] = "6"

    def test_vrf_tab_follows_family(self):
        r = self.client.get(reverse("ipam:vrf_tree", kwargs={"pk": self.t["red"].pk}))
        self.assertContains(r, 'data-ipt-action="family"')
        self.assertContains(r, "2001:db8::/32")
        self.assertNotContains(r, "10.1.0.0/16")
        params = {"tab": tab_key("vrf", self.t["red"].pk), "all": "1", "af": "4", "free": "0"}
        r = self.client.get(reverse(NS + "expand"), params)
        self.assertContains(r, "10.1.9.0/24")
        self.assertNotContains(r, "2001:db8:2::/48")

    def test_prefix_and_aggregate_tabs_ignore_family(self):
        # A prefix or an aggregate has a single family: its tab always shows it, whatever was chosen elsewhere.
        r = self.client.get(reverse("ipam:prefix_tree", kwargs={"pk": self.t["p16"].pk}))
        self.assertContains(r, "10.1.1.0/24")
        self.assertNotContains(r, 'data-ipt-action="family"')
        self.assertContains(r, 'data-family=""')
        r = self.client.get(reverse("ipam:aggregate_tree", kwargs={"pk": self.t["agg"].pk}))
        self.assertContains(r, f'data-key="agg:{self.t["agg"].pk}@0"')
        params = {"tab": tab_key("prefix", self.t["p16"].pk), "all": "1", "free": "0"}
        self.assertContains(self.client.get(reverse(NS + "expand"), params), "10.1.1.0/26")
