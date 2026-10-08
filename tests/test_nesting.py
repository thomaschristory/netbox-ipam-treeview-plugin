from netaddr import IPNetwork as N

from netbox_ipam_treeview.tree.nesting import ANY, Item, nest


def shape(nested):
    return [(n.item.payload, n.depth, None if n.parent is None else nested[n.parent].item.payload) for n in nested]


def test_nest_simple_chain():
    res = nest([Item(N("10.0.1.0/24"), "c", 1), Item(N("10.0.0.0/16"), "a", 1), Item(N("10.0.0.0/20"), "b", 1)])
    assert shape(res) == [("a", 0, None), ("b", 1, "a"), ("c", 2, "b")]


def test_nest_siblings():
    res = nest([Item(N("10.0.0.0/24"), "a", 1), Item(N("10.0.1.0/24"), "b", 1)])
    assert shape(res) == [("a", 0, None), ("b", 0, None)]


def test_nest_duplicates_are_siblings():
    res = nest([Item(N("10.0.0.0/24"), "a", 1), Item(N("10.0.0.0/24"), "b", 1), Item(N("10.0.0.0/26"), "c", 1)])
    assert [r.depth for r in res] == [0, 0, 1]
    assert res[2].parent == 1


def test_nest_inclusive_aggregate_contains_equal_prefix():
    res = nest([Item(N("10.0.0.0/8"), "p", 1), Item(N("10.0.0.0/8"), "agg", ANY, inclusive=True)])
    assert shape(res) == [("agg", 0, None), ("p", 1, "agg")]


def test_nest_respects_vrf():
    res = nest(
        [
            Item(N("10.0.0.0/16"), "g16", None),
            Item(N("10.0.1.0/24"), "corp24", 7),
            Item(N("10.0.2.0/24"), "g24", None),
        ]
    )
    assert shape(res) == [("g16", 0, None), ("g24", 1, "g16"), ("corp24", 0, None)]


def test_nest_aggregate_spans_vrfs():
    res = nest(
        [
            Item(N("10.0.0.0/8"), "agg", ANY, inclusive=True),
            Item(N("10.1.0.0/16"), "corp", 7),
            Item(N("10.1.0.0/16"), "glob", None),
            Item(N("10.1.1.0/24"), "corp24", 7),
        ]
    )
    assert shape(res) == [("agg", 0, None), ("corp", 1, "agg"), ("corp24", 2, "corp"), ("glob", 1, "agg")]


def test_nest_ipv4_before_ipv6():
    res = nest([Item(N("fd00::/8"), "v6", None), Item(N("10.0.0.0/8"), "v4", None)])
    assert [r.item.payload for r in res] == ["v4", "v6"]


def test_nest_aggregate_ends_scope():
    res = nest(
        [
            Item(N("10.0.0.0/8"), "agg", ANY, inclusive=True),
            Item(N("10.1.0.0/16"), "in", None),
            Item(N("11.0.0.0/16"), "out", None),
        ]
    )
    assert shape(res) == [("agg", 0, None), ("in", 1, "agg"), ("out", 0, None)]


def test_nest_aggregate_inside_open_prefix_is_dropped():
    # A prefix wider than an aggregate (e.g. 0.0.0.0/0) keeps its children; the aggregate is not a root under it.
    res = nest(
        [
            Item(N("10.0.0.0/7"), "p7", None),
            Item(N("10.0.0.0/8"), "agg", ANY, inclusive=True),
            Item(N("10.1.0.0/16"), "p16", None),
            Item(N("11.0.0.0/16"), "p11", None),
        ]
    )
    assert shape(res) == [("p7", 0, None), ("p16", 1, "p7"), ("p11", 1, "p7")]
