from netbox_ipam_treeview import __version__, config
from netbox_ipam_treeview.conf import DEFAULTS, PLUGIN_NAME


def test_version():
    assert __version__ == "0.1.1"


def test_config_is_module_level():
    assert config.name == PLUGIN_NAME
    assert config.version == __version__
    assert config.base_url == "ipam-tree"
    assert config.default_settings is DEFAULTS


def test_defaults_cover_spec_keys():
    assert DEFAULTS["expand_all_limit"] == 5000
    assert DEFAULTS["max_gap_rows"] == 64
