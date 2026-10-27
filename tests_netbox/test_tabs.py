from django.urls import reverse
from utilities.testing import TestCase

from netbox_ipam_treeview.conf import FREE_COOKIE
from netbox_ipam_treeview.tree.nodes import pfx_key, tab_key
from netbox_ipam_treeview.version import __version__

from .fixtures import VIEW_PERMISSIONS, make_tree

TREE = "plugins:netbox_ipam_treeview:tree"
EXPAND = "plugins:netbox_ipam_treeview:expand"
GAP_ROW = 'class="ipt-row ipt-gap'


class TabTest(TestCase):
    user_permissions = VIEW_PERMISSIONS

    def setUp(self):
        super().setUp()
        self.t = make_tree()

    def test_prefix_tab(self):
        r = self.client.get(reverse("ipam:prefix_tree", kwargs={"pk": self.t["p16"].pk}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "10.1.1.0/24")
        self.assertContains(r, f'data-root-key="pfx:{self.t["p16"].pk}"')
        self.assertContains(r, f"netbox_ipam_treeview/tree.js?v={__version__}")
        self.assertContains(r, f"netbox_ipam_treeview/tree.css?v={__version__}")

    def test_aggregate_tab_lists_each_vrf(self):
        agg = self.t["agg"].pk
        r = self.client.get(reverse("ipam:aggregate_tree", kwargs={"pk": agg}))
        self.assertContains(r, f'data-key="agg:{agg}@0"')
        self.assertContains(r, f'data-key="agg:{agg}@{self.t["red"].pk}"')
        self.assertContains(r, "RED")

    def test_vrf_tab(self):
        r = self.client.get(reverse("ipam:vrf_tree", kwargs={"pk": self.t["red"].pk}))
        self.assertContains(r, "10.1.0.0/16")

    def test_tab_link_on_prefix_page(self):
        r = self.client.get(reverse("ipam:prefix", kwargs={"pk": self.t["p16"].pk}))
        self.assertContains(r, reverse("ipam:prefix_tree", kwargs={"pk": self.t["p16"].pk}))

    def test_tab_hidden_when_disabled(self):
        url = reverse("ipam:prefix_tree", kwargs={"pk": self.t["p16"].pk})
        with self.settings(PLUGINS_CONFIG={"netbox_ipam_treeview": {"show_prefix_tab": False}}):
            r = self.client.get(reverse("ipam:prefix", kwargs={"pk": self.t["p16"].pk}))
            self.assertNotContains(r, url)
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_list_toggle_button(self):
        r = self.client.get(reverse("ipam:prefix_list") + "?status=active")
        self.assertContains(r, reverse(TREE) + "?status=active")

    def test_list_toggle_disabled(self):
        with self.settings(PLUGINS_CONFIG={"netbox_ipam_treeview": {"show_list_toggle": False}}):
            r = self.client.get(reverse("ipam:prefix_list"))
            self.assertNotContains(r, 'class="btn btn-outline-primary ipt-tree-toggle"')


class TabStateTest(TestCase):
    """Saved expansion state and the free-space preference on Tree tabs (#24)."""

    user_permissions = VIEW_PERMISSIONS

    def setUp(self):
        super().setUp()
        self.t = make_tree()
        self.url = reverse("ipam:prefix_tree", kwargs={"pk": self.t["p16"].pk})

    def test_tab_names_its_object_for_restore(self):
        r = self.client.get(self.url)
        self.assertContains(r, f'data-tab="{tab_key("prefix", self.t["p16"].pk)}"')
        self.assertContains(r, f'data-storage-key="ipam-tree:prefix:{self.t["p16"].pk}"')
        r = self.client.get(reverse("ipam:vrf_tree", kwargs={"pk": self.t["red"].pk}))
        self.assertContains(r, f'data-tab="{tab_key("vrf", self.t["red"].pk)}"')

    def test_main_page_has_no_tab(self):
        self.assertContains(self.client.get(reverse(TREE)), 'data-tab=""')

    def test_free_space_follows_setting_by_default(self):
        self.assertContains(self.client.get(self.url), GAP_ROW)

    def test_remembered_free_space_off_applies_to_initial_rows(self):
        self.client.cookies[FREE_COOKIE] = "0"
        r = self.client.get(self.url)
        self.assertNotContains(r, GAP_ROW)
        self.assertContains(r, 'data-free="0"')
        self.assertNotContains(r, 'data-ipt-action="toggle-free" checked')

    def test_remembered_free_space_on_overrides_setting(self):
        self.client.cookies[FREE_COOKIE] = "1"
        with self.settings(PLUGINS_CONFIG={"netbox_ipam_treeview": {"show_free_space": False}}):
            r = self.client.get(self.url)
        self.assertContains(r, GAP_ROW)

    def test_url_parameter_wins_over_cookie(self):
        self.client.cookies[FREE_COOKIE] = "0"
        self.assertContains(self.client.get(self.url, {"free": "1"}), GAP_ROW)

    def test_expand_restores_tab_tree(self):
        p16, p24 = pfx_key(self.t["p16"].pk), pfx_key(self.t["p24"].pk)
        params = {"tab": tab_key("prefix", self.t["p16"].pk), "keys": f"{p16},{p24}", "free": "0"}
        r = self.client.get(reverse(EXPAND), params)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "10.1.1.0/26")
        self.assertNotContains(r, 'data-key="vrf:')  # rooted at the tab's prefix, not the page's VRF groups
        self.assertNotContains(r, GAP_ROW)

    def test_expand_tab_with_nothing_open(self):
        r = self.client.get(reverse(EXPAND), {"tab": tab_key("prefix", self.t["p16"].pk), "keys": ""})
        self.assertContains(r, f'data-key="{pfx_key(self.t["p16"].pk)}"')
        self.assertNotContains(r, 'data-key="vrf:')  # rooted at the tab's prefix even with nothing open
        self.assertContains(r, 'aria-expanded="false"')
        self.assertNotContains(r, "10.1.1.0/24")

    def test_expand_aggregate_tab(self):
        agg, red = self.t["agg"].pk, self.t["red"].pk
        r = self.client.get(reverse(EXPAND), {"tab": tab_key("aggregate", agg), "keys": f"agg:{agg}@{red}"})
        self.assertContains(r, f'data-key="agg:{agg}@0"')
        self.assertContains(r, f'data-key="{pfx_key(self.t["r16"].pk)}"')
        self.assertNotContains(r, f'data-key="{pfx_key(self.t["p16"].pk)}"')

    def test_expand_all_restores_whole_tab_tree(self):
        # "Expand all" on a tab is saved as {all: true} and restored with all=1, not as a capped list of keys.
        p16, p24 = pfx_key(self.t["p16"].pk), pfx_key(self.t["p24"].pk)
        r = self.client.get(reverse(EXPAND), {"tab": tab_key("prefix", self.t["p16"].pk), "all": "1", "free": "0"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("X-Tree-Truncated", r)
        self.assertContains(r, "10.1.1.0/26")
        self.assertNotContains(r, 'data-key="vrf:')
        self.assertNotContains(r, "10.1.9.0/24")  # the VRF RED twin of 10.1.0.0/16 is not under this tab
        for key in (p16, p24):
            self.assertContains(r, f'data-key="{key}"')
        self.assertNotContains(r, 'aria-expanded="false"')

    def test_expand_all_aggregate_tab(self):
        agg = self.t["agg"].pk
        r = self.client.get(reverse(EXPAND), {"tab": tab_key("aggregate", agg), "all": "1", "free": "0"})
        for p in ("p16", "p24", "p26", "r16", "r24"):
            self.assertContains(r, f'data-key="{pfx_key(self.t[p].pk)}"')
        self.assertNotContains(r, f'data-key="{pfx_key(self.t["orphan"].pk)}"')

    def test_expand_all_tab_truncated(self):
        params = {"tab": tab_key("aggregate", self.t["agg"].pk), "all": "1", "free": "0"}
        with self.settings(PLUGINS_CONFIG={"netbox_ipam_treeview": {"expand_all_limit": 2}}):
            r = self.client.get(reverse(EXPAND), params)
        self.assertEqual(r["X-Tree-Truncated"], "1")
        self.assertContains(r, f'data-key="{pfx_key(self.t["p16"].pk)}"')
        self.assertNotContains(r, f'data-key="{pfx_key(self.t["r24"].pk)}"')

    def test_expand_all_unknown_tab_404(self):
        r = self.client.get(reverse(EXPAND), {"tab": "prefix:999999", "all": "1"})
        self.assertEqual(r.status_code, 404)

    def test_expand_unknown_tab_404(self):
        for tab in ("prefix:999999", "vrf:999999", "garbage"):
            r = self.client.get(reverse(EXPAND), {"tab": tab, "keys": ""})
            self.assertEqual(r.status_code, 404, tab)

    def test_expand_tab_hidden_from_user_404(self):
        self.remove_permissions("ipam.view_vrf")
        r = self.client.get(reverse(EXPAND), {"tab": tab_key("vrf", self.t["red"].pk), "keys": ""})
        self.assertEqual(r.status_code, 404)
