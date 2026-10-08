from netbox.plugins import PluginMenuItem

from .conf import get_setting

LINK = "plugins:netbox_ipam_treeview:tree"
LABEL = "Prefix Tree"
PERMISSIONS = ["ipam.view_prefix"]


def _add_to_ipam_menu():
    """Put the tree at the top of NetBox's IPAM menu.

    Plugins have no API for core menus, so this prepends a group to IPAM_MENU (a plain dataclass, the same in
    NetBox 4.5-4.7). Returns False when the menu module looks different, and the caller falls back to the
    Plugins menu.
    """
    try:
        from netbox.navigation import MenuGroup, MenuItem
        from netbox.navigation.menu import IPAM_MENU
    except ImportError:
        return False
    if not hasattr(IPAM_MENU, "groups"):
        return False
    if any(item.link == LINK for group in IPAM_MENU.groups for item in group.items):
        return True
    entry = MenuGroup(label="Tree View", items=(MenuItem(link=LINK, link_text=LABEL, permissions=PERMISSIONS),))
    IPAM_MENU.groups = (entry, *IPAM_MENU.groups)
    return True


_show = get_setting("show_menu_item")
_in_ipam = _show and get_setting("menu_location") == "ipam" and _add_to_ipam_menu()

menu_items = (PluginMenuItem(link=LINK, link_text=LABEL, permissions=PERMISSIONS),) if _show and not _in_ipam else ()
