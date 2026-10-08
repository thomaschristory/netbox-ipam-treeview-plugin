from netbox_ipam_alt_view import __version__
from netbox_ipam_alt_view.conf import DEFAULTS


def test_version():
    assert __version__ == "0.1.0"


def test_defaults_cover_spec_keys():
    assert DEFAULTS["expand_all_limit"] == 5000
    assert DEFAULTS["max_gap_rows"] == 64
