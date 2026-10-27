"""Pure unit tests run without NetBox: stub netbox.plugins so the package's __init__ imports."""

import sys
import types

try:
    import netbox.plugins  # noqa: F401
except ImportError:

    class PluginConfig:
        pass

    netbox = types.ModuleType("netbox")
    plugins = types.ModuleType("netbox.plugins")
    plugins.PluginConfig = PluginConfig
    netbox.plugins = plugins
    sys.modules.update({"netbox": netbox, "netbox.plugins": plugins})
