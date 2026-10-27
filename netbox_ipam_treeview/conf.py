PLUGIN_NAME = "netbox_ipam_treeview"
# Mirrors the free-space switch (kept in localStorage by tree.js) so the server renders the first rows to match.
FREE_COOKIE = "ipam_tree_free"

DEFAULTS = {
    "show_menu_item": True,
    "menu_location": "menu",  # "menu": own top-level menu; "plugins": the Plugins menu; "ipam": below IPAM "Prefixes"
    "show_list_toggle": True,
    "show_prefix_tab": True,
    "show_aggregate_tab": True,
    "show_vrf_tab": True,
    "group_by_vrf": True,
    "show_aggregates": True,
    "show_free_space": True,
    "gaps_respect_mark_utilized": True,
    "max_gap_rows": 64,
    "expand_all_limit": 5000,
    "default_columns": ["status", "utilization", "scope", "vlan", "tenant", "role", "description", "actions"],
}


def get_setting(key):
    from netbox.plugins.utils import get_plugin_config

    return get_plugin_config(PLUGIN_NAME, key, DEFAULTS[key])


def free_preference(query, cookie, default):
    """Free-space rows on or off: the ?free= parameter wins, then the browser's remembered choice, then the setting."""
    if query is not None:
        return query == "1"
    if cookie in ("0", "1"):
        return cookie == "1"
    return default
