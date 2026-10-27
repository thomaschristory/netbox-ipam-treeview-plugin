import logging

from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginMenu, PluginMenuItem

from .conf import get_setting

LINK = "plugins:netbox_ipam_treeview:tree"
LABEL = _("Prefix Tree")
PERMISSIONS = ["ipam.view_prefix"]
MENU_LABEL = _("IPAM Tree")
MENU_ICON = "mdi mdi-file-tree"
LOCATIONS = ("menu", "plugins", "ipam")

logger = logging.getLogger("netbox_ipam_treeview")


def _add_to_ipam_menu(ipam_menu=None):
    """Insert the tree right after "Prefixes" in NetBox's IPAM menu.

    Plugins have no API for core menus, so this edits IPAM_MENU (plain dataclasses in NetBox 4.7).
    Returns False when the menu looks different, and the caller falls back to the plugin's own menu.
    """
    try:
        from netbox.navigation import MenuItem
        from netbox.navigation.menu import IPAM_MENU
    except ImportError:
        return False
    if ipam_menu is None:
        ipam_menu = IPAM_MENU
    groups = getattr(ipam_menu, "groups", ())
    if any(item.link == LINK for group in groups for item in group.items):
        return True
    for group in groups:
        links = [item.link for item in group.items]
        if "ipam:prefix_list" in links:
            at = links.index("ipam:prefix_list") + 1
            entry = MenuItem(link=LINK, link_text=LABEL, permissions=PERMISSIONS)
            group.items = (*group.items[:at], entry, *group.items[at:])
            return True
    return False


def build(show, location, ipam_menu=None):
    """Return (menu, menu_items) for NetBox's plugin loader.

    "menu" (default): the plugin's own top-level menu. "plugins": the shared Plugins menu. "ipam": opt-in patch of
    the IPAM menu, falling back to the plugin's own menu when the patch does not apply.
    """
    if not show:
        return None, ()
    if location not in LOCATIONS:
        logger.warning('Unknown menu_location %r (expected one of %s); using "menu"', location, ", ".join(LOCATIONS))
    if location == "ipam" and _add_to_ipam_menu(ipam_menu):
        return None, ()
    item = PluginMenuItem(link=LINK, link_text=LABEL, permissions=PERMISSIONS)
    if location == "plugins":
        return None, (item,)
    return PluginMenu(label=MENU_LABEL, groups=((_("Prefixes"), (item,)),), icon_class=MENU_ICON), ()


menu, menu_items = build(get_setting("show_menu_item"), get_setting("menu_location"))
