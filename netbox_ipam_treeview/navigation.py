from netbox.plugins import PluginMenuItem

from .conf import get_setting

menu_items = (
    (
        PluginMenuItem(
            link="plugins:netbox_ipam_treeview:tree",
            link_text="Prefix Tree",
            permissions=["ipam.view_prefix"],
        ),
    )
    if get_setting("show_menu_item")
    else ()
)
