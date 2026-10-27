import copy

from django.test import SimpleTestCase
from django.utils.functional import Promise
from netbox.navigation.menu import IPAM_MENU
from netbox.registry import registry

from netbox_ipam_treeview import navigation

TREE = "plugins:netbox_ipam_treeview:tree"


def links(menu):
    return [item.link for group in menu.groups for item in group.items]


class DefaultMenuTest(SimpleTestCase):
    """The dev and CI configs use the defaults: the plugin's own menu, IPAM menu untouched."""

    def test_own_menu_registered(self):
        menu = next(m for m in registry["plugins"]["menus"] if TREE in links(m))
        self.assertEqual(str(menu.label), "IPAM Tree")
        self.assertEqual(menu.icon_class, "mdi mdi-file-tree")

    def test_ipam_menu_untouched(self):
        self.assertNotIn(TREE, links(IPAM_MENU))

    def test_listed_once(self):
        menu_links = [link for m in registry["plugins"]["menus"] for link in links(m)]
        plugin_links = [item.link for items in registry["plugins"]["menu_items"].values() for item in items]
        self.assertEqual((links(IPAM_MENU) + menu_links + plugin_links).count(TREE), 1)

    def test_label_is_translatable(self):
        self.assertIsInstance(navigation.LABEL, Promise)
        self.assertEqual(str(navigation.LABEL), "Prefix Tree")


class MenuLocationTest(SimpleTestCase):
    def setUp(self):
        self.ipam = copy.deepcopy(IPAM_MENU)

    def test_menu(self):
        menu, items = navigation.build(True, "menu", self.ipam)
        self.assertEqual(links(menu), [TREE])
        self.assertEqual(items, ())
        self.assertNotIn(TREE, links(self.ipam))

    def test_plugins(self):
        menu, items = navigation.build(True, "plugins", self.ipam)
        self.assertIsNone(menu)
        self.assertEqual([i.link for i in items], [TREE])
        self.assertNotIn(TREE, links(self.ipam))

    def test_ipam_follows_prefixes(self):
        menu, items = navigation.build(True, "ipam", self.ipam)
        self.assertEqual((menu, items), (None, ()))
        group = next(g for g in self.ipam.groups if any(i.link == "ipam:prefix_list" for i in g.items))
        self.assertEqual([i.link for i in group.items][:2], ["ipam:prefix_list", TREE])
        # Idempotent: a second patch does not add a duplicate.
        navigation.build(True, "ipam", self.ipam)
        self.assertEqual(links(self.ipam).count(TREE), 1)

    def test_ipam_falls_back_to_own_menu(self):
        for group in self.ipam.groups:
            group.items = tuple(i for i in group.items if i.link != "ipam:prefix_list")
        menu, items = navigation.build(True, "ipam", self.ipam)
        self.assertEqual(links(menu), [TREE])
        self.assertNotIn(TREE, links(self.ipam))

    def test_hidden(self):
        for location in ("menu", "plugins", "ipam"):
            self.assertEqual(navigation.build(False, location, self.ipam), (None, ()), location)
        self.assertNotIn(TREE, links(self.ipam))

    def test_unknown_location_uses_own_menu(self):
        menu, items = navigation.build(True, "bogus", self.ipam)
        self.assertEqual(links(menu), [TREE])
