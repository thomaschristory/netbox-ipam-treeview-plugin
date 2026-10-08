"""Prefix utilization math, mirroring Prefix.get_utilization() in NetBox 4.7. Pure: netaddr only."""

from bisect import bisect_left, bisect_right

import netaddr


def merge_intervals(intervals):
    """Merge overlapping or adjacent (start, end) integer intervals."""
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def container_utilization(network, child_networks):
    """Share of `network` covered by the union of its child prefixes, in percent."""
    network = netaddr.IPNetwork(network)
    covered = netaddr.IPSet(child_networks).size
    return min(float(covered) / network.size * 100, 100.0)


def _count_between(sorted_hosts, start, end):
    return bisect_right(sorted_hosts, end) - bisect_left(sorted_hosts, start)


def host_utilization(network, is_pool, sorted_hosts, utilized_intervals):
    """Utilization of a non-container prefix, in percent.

    `sorted_hosts`: sorted distinct host addresses (ints) of the prefix's VRF, may extend beyond the prefix.
    `utilized_intervals`: (start, end) ints of mark_utilized IP ranges lying inside the prefix.
    """
    network = netaddr.IPNetwork(network)
    size = network.size
    if network.version == 4 and network.prefixlen < 31 and not is_pool:
        size -= 2
    intervals = merge_intervals(utilized_intervals)
    range_count = sum(end - start + 1 for start, end in intervals)
    if range_count >= size:
        return 100.0
    ip_count = _count_between(sorted_hosts, network.first, network.last)
    ip_count -= sum(_count_between(sorted_hosts, start, end) for start, end in intervals)
    return min(float(range_count + ip_count) / size * 100, 100.0)
