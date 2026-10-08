from django.test import TestCase
from django.urls import reverse

from .fixtures import make_tree, superuser

TREE = "plugins:netbox_ipam_treeview:tree"


class TabTest(TestCase):
    def setUp(self):
        self.t = make_tree()
        self.client.force_login(superuser())

    def test_prefix_tab(self):
        r = self.client.get(reverse("ipam:prefix_tree", kwargs={"pk": self.t["p16"].pk}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "10.1.1.0/24")
        self.assertContains(r, f'data-root-key="pfx:{self.t["p16"].pk}"')

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
