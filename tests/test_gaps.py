from netaddr import IPNetwork as N

from netbox_ipam_treeview.tree.gaps import free_blocks, interleave


def test_free_blocks_no_children():
    assert free_blocks(N("10.0.0.0/22"), []) == [N("10.0.0.0/22")]


def test_free_blocks_partial():
    assert free_blocks(N("10.0.0.0/22"), [N("10.0.1.0/24")]) == [N("10.0.0.0/24"), N("10.0.2.0/23")]


def test_free_blocks_full():
    assert free_blocks(N("10.0.0.0/23"), [N("10.0.0.0/24"), N("10.0.1.0/24")]) == []


def test_interleave_orders_children_and_gaps():
    out = interleave(N("10.0.0.0/22"), [(N("10.0.1.0/24"), "a"), (N("10.0.3.0/24"), "b")], max_gaps=10)
    assert out == [("gap", N("10.0.0.0/24")), ("child", "a"), ("gap", N("10.0.2.0/24")), ("child", "b")]


def test_interleave_without_gaps():
    out = interleave(N("10.0.0.0/22"), [(N("10.0.1.0/24"), "a")], max_gaps=10, with_gaps=False)
    assert out == [("child", "a")]


def test_interleave_caps_gaps():
    out = interleave(N("fd00::/32"), [(N("fd00:0:ffff::/64"), "x")], max_gaps=4)
    gaps = [o for o in out if o[0] == "gap"]
    more = [o for o in out if o[0] == "more"]
    assert len(gaps) == 4
    assert len(more) == 1 and more[0][1][0] > 0
    assert out[-1][0] == "more"
    assert ("child", "x") in out


def test_interleave_ipv6_children_sorted():
    out = interleave(N("fd00::/16"), [(N("fd00:2::/32"), "b"), (N("fd00:1::/32"), "a")], max_gaps=100)
    assert [p for k, p in out if k == "child"] == ["a", "b"]
