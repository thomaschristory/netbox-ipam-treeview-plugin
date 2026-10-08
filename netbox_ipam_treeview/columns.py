from django.utils.translation import gettext_lazy as _

from .conf import get_setting

USER_CONFIG_PATH = "plugins.netbox_ipam_treeview.columns"

COLUMNS = {
    "status": _("Status"),
    "utilization": _("Utilization"),
    "vrf": _("VRF"),
    "scope": _("Scope"),
    "vlan": _("VLAN"),
    "tenant": _("Tenant"),
    "role": _("Role"),
    "children": _("Children"),
    "is_pool": _("Pool"),
    "mark_utilized": _("Marked utilized"),
    "tags": _("Tags"),
    "description": _("Description"),
    "created": _("Created"),
    "last_updated": _("Last updated"),
    "actions": "",
}


def resolve_columns(user):
    """The user's saved column choice, else the configured default, limited to known columns."""
    chosen = None
    if getattr(user, "is_authenticated", False) and hasattr(user, "config"):
        chosen = user.config.get(USER_CONFIG_PATH)
    chosen = chosen or get_setting("default_columns")
    return [c for c in chosen if c in COLUMNS]
