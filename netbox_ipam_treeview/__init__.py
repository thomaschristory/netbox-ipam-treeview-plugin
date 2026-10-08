from .conf import DEFAULTS
from .version import __version__

try:
    from netbox.plugins import PluginConfig
except ImportError:  # imported outside NetBox (pure unit tests, build tools)
    PluginConfig = None

if PluginConfig is not None:

    class IPAMAltViewConfig(PluginConfig):
        name = "netbox_ipam_treeview"
        verbose_name = "IPAM Tree"
        description = "DDI-style collapsible tree view for NetBox IPAM prefixes"
        version = __version__
        author = "Thomas Christory"
        author_email = "9317624+thomaschristory@users.noreply.github.com"
        base_url = "ipam-tree"
        min_version = "4.5.0"
        max_version = "4.7.99"
        default_settings = DEFAULTS

    config = IPAMAltViewConfig
