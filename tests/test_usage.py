from netaddr import IPAddress as A
from netaddr import IPNetwork as N

from netbox_ipam_treeview.tree.usage import (
    MAX_COVER_CLAUSES,
    container_utilization,
    cover_blocks,
    host_utilization,
    merge_intervals,
)


def test_container_utilization_counts_union_of_children():
    assert container_utilization(N("10.0.0.0/22"), [N("10.0.0.0/24"), N("10.0.0.0/25"), N("10.0.2.0/24")]) == 50.0


def test_container_utilization_empty():
    assert container_utilization(N("10.0.0.0/22"), []) == 0.0


def test_host_utilization_excludes_network_and_broadcast_for_ipv4():
    hosts = [int(A("10.0.0.1")), int(A("10.0.0.2"))]
    assert host_utilization(N("10.0.0.0/30"), False, hosts, []) == 100.0


def test_host_utilization_pool_uses_full_size():
    assert host_utilization(N("10.0.0.0/30"), True, [int(A("10.0.0.1"))], []) == 25.0


def test_host_utilization_ranges_and_dedup():
    hosts = sorted([int(A("10.0.0.5")), int(A("10.0.0.20")), int(A("10.0.0.21"))])
    ranges = [(int(A("10.0.0.16")), int(A("10.0.0.31")))]  # 16 addresses, swallows .20 and .21
    # (16 + 1) / 254
    assert host_utilization(N("10.0.0.0/24"), False, hosts, ranges) == 17 / 254 * 100


def test_host_utilization_capped():
    hosts = list(range(int(A("10.0.0.0")), int(A("10.0.0.4"))))
    assert host_utilization(N("10.0.0.0/30"), False, hosts, []) == 100.0


def test_merge_intervals():
    assert merge_intervals([(5, 9), (1, 3), (4, 4), (12, 13)]) == [(1, 9), (12, 13)]


def test_cover_blocks_merges_nested_and_adjacent():
    assert cover_blocks(["10.0.0.0/24", "10.0.1.0/24", "10.0.0.0/25", "2001:db8::/64"]) == [
        N("10.0.0.0/23"),
        N("2001:db8::/64"),
    ]


def test_cover_blocks_spans_per_version_above_limit():
    v4 = [f"10.{i}.0.0/24" for i in range(0, 2 * (MAX_COVER_CLAUSES + 1), 2)]
    v6 = ["2001:db8::/48", "2001:db8:2::/48"]
    assert cover_blocks(v4 + v6) == [N("10.0.0.0/8"), N("2001:db8::/46")]


def test_cover_blocks_single_block_family_above_limit():
    # Regression: spanning_cidr() raised ValueError for a family that merged into a single block.
    v4 = [f"10.{i}.0.0/24" for i in range(0, 2 * (MAX_COVER_CLAUSES + 1), 2)]
    assert cover_blocks(v4 + ["2001:db8::/32", "2001:db8::/64"]) == [N("10.0.0.0/8"), N("2001:db8::/32")]
