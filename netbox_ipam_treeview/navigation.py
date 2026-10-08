from netbox.plugins import PluginMenuItem

from .conf import get_setting

LINK = "plugins:netbox_ipam_treeview:tree"
LABEL = "Prefix Tree"
PERMISSIONS = ["ipam.view_prefix"]


def _add_to_ipam_menu():
    """Insert the tree right after "Prefixes" in NetBox's IPAM menu.

    Plugins have no API for core menus, so this edits IPAM_MENU (plain dataclasses, the same in NetBox 4.5-4.7).
    Returns False when the menu looks different, and the caller falls back to the Plugins menu.
    """
    try:
        from netbox.navigation import MenuItem
        from netbox.navigation.menu import IPAM_MENU
    except ImportError:
        return False
    groups = getattr(IPAM_MENU, "groups", ())
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


_show = get_setting("show_menu_item")
_in_ipam = _show and get_setting("menu_location") == "ipam" and _add_to_ipam_menu()

menu_items = (PluginMenuItem(link=LINK, link_text=LABEL, permissions=PERMISSIONS),) if _show and not _in_ipam else ()
