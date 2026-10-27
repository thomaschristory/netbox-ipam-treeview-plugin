"""Prefix utilization math, mirroring Prefix.get_utilization() in NetBox 4.7. Pure: netaddr only."""

from bisect import bisect_left, bisect_right

import netaddr

# Above this many disjoint blocks, cover_blocks() returns one spanning block per IP version instead.
MAX_COVER_CLAUSES = 64


def cover_blocks(networks, max_blocks=MAX_COVER_CLAUSES):
    """Minimal CIDR blocks covering every network; each network lies inside exactly one of them."""
    blocks = netaddr.IPSet(networks).iter_cidrs()
    if len(blocks) > max_blocks:
        by_version = {}
        for b in blocks:
            by_version.setdefault(b.version, []).append(b)
        # spanning_cidr() needs at least two networks; a family that merged into one block is its own cover.
        blocks = [bs[0] if len(bs) == 1 else netaddr.spanning_cidr(bs) for bs in by_version.values()]
    return blocks


class NetworkIndex:
    """Networks sorted by address, for quick "which of them lie inside this network" lookups."""

    def __init__(self, networks):
        self.networks = sorted(
            (netaddr.IPNetwork(n) for n in networks), key=lambda n: (n.version, n.first, n.prefixlen)
        )
        self._keys = [(n.version, n.first) for n in self.networks]

    def within(self, network, *, or_equal=False):
        """Indexed networks inside `network`; `or_equal` also returns networks equal to it."""
        network = netaddr.IPNetwork(network)
        lo = bisect_left(self._keys, (network.version, network.first))
        hi = bisect_right(self._keys, (network.version, network.last))
        # A CIDR block starting inside `network` is either inside it or (same start, shorter mask) contains it.
        return [
            n
            for n in self.networks[lo:hi]
            if n.prefixlen > network.prefixlen or (or_equal and n.prefixlen == network.prefixlen)
        ]


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
