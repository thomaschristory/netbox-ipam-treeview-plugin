PLUGIN_NAME = "netbox_ipam_alt_view"

DEFAULTS = {
    "show_menu_item": True,
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
