from django.test import SimpleTestCase
from netbox.navigation.menu import IPAM_MENU
from netbox.registry import registry

TREE = "plugins:netbox_ipam_treeview:tree"


class MenuTest(SimpleTestCase):
    def test_tree_link_is_first_in_ipam_menu(self):
        first_group = IPAM_MENU.groups[0]
        self.assertEqual([item.link for item in first_group.items], [TREE])

    def test_not_duplicated_in_plugins_menu(self):
        links = [item.link for items in registry["plugins"]["menu_items"].values() for item in items]
        self.assertNotIn(TREE, links)
