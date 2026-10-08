from django.test import SimpleTestCase
from netbox.navigation.menu import IPAM_MENU
from netbox.registry import registry

TREE = "plugins:netbox_ipam_treeview:tree"


class MenuTest(SimpleTestCase):
    def test_tree_link_follows_prefixes_in_ipam_menu(self):
        group = next(g for g in IPAM_MENU.groups if any(i.link == "ipam:prefix_list" for i in g.items))
        links = [item.link for item in group.items]
        self.assertEqual(links[:2], ["ipam:prefix_list", TREE])

    def test_listed_once(self):
        ipam_links = [item.link for group in IPAM_MENU.groups for item in group.items]
        plugin_links = [item.link for items in registry["plugins"]["menu_items"].values() for item in items]
        self.assertEqual((ipam_links + plugin_links).count(TREE), 1)
