import pytest

from netbox_ipam_alt_view.tree.nodes import ALL_VRFS, agg_key, parse_key, pfx_key, vrf_key


def test_keys_roundtrip():
    assert parse_key(vrf_key(None)) == ("vrf", 0, None)
    assert parse_key(vrf_key(3)) == ("vrf", 3, 3)
    assert parse_key(agg_key(5, None)) == ("aggregate", 5, None)
    assert parse_key(agg_key(5, 9)) == ("aggregate", 5, 9)
    assert parse_key(agg_key(5, ALL_VRFS)) == ("aggregate", 5, ALL_VRFS)
    assert parse_key(pfx_key(42)) == ("prefix", 42, None)


@pytest.mark.parametrize("bad", ["", "pfx:", "pfx:abc", "agg:1", "zzz:1", "agg:x@1", "vrf:-1", "pfx:1@2"])
def test_parse_key_rejects(bad):
    with pytest.raises(ValueError):
        parse_key(bad)
