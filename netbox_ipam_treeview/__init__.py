from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginConfig

from .conf import DEFAULTS
from .version import __version__


class IPAMAltViewConfig(PluginConfig):
    name = "netbox_ipam_treeview"
    verbose_name = _("IPAM Tree")
    description = _("DDI-style collapsible tree view for NetBox IPAM prefixes")
    version = __version__
    author = "Thomas Christory"
    author_email = "9317624+thomaschristory@users.noreply.github.com"
    base_url = "ipam-tree"
    min_version = "4.7.2"
    max_version = "4.7.99"
    default_settings = DEFAULTS


config = IPAMAltViewConfig
