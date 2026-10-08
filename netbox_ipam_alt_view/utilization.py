"""Batched prefix utilization: a constant number of queries per VRF instead of two per prefix."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from functools import reduce
from operator import or_

import netaddr
from django.db.models import Q
from ipam.choices import PrefixStatusChoices
from ipam.models import IPAddress, IPRange, Prefix

from .tree.usage import container_utilization, host_utilization

# Above this many disjoint blocks, query one spanning block per IP version instead of OR-ing them all.
MAX_COVER_CLAUSES = 64


def _vrf_q(vrf_id):
    return Q(vrf__isnull=True) if vrf_id is None else Q(vrf_id=vrf_id)


def _cover(prefixes):
    """Minimal CIDR blocks covering every prefix; each prefix lies inside exactly one of them."""
    blocks = netaddr.IPSet(p.prefix for p in prefixes).iter_cidrs()
    if len(blocks) > MAX_COVER_CLAUSES:
        by_version = defaultdict(list)
        for b in blocks:
            by_version[b.version].append(b)
        blocks = [netaddr.spanning_cidr(bs) for bs in by_version.values()]
    return blocks


def _within(field, blocks):
    return reduce(or_, (Q(**{f"{field}__net_host_contained": str(b)}) for b in blocks))


def _container_values(vrf_id, group):
    blocks = _cover(group)
    lookup = reduce(or_, (Q(prefix__net_contained_or_equal=str(b)) for b in blocks))
    nets = sorted(
        (
            netaddr.IPNetwork(n)
            for n in Prefix.objects.filter(_vrf_q(vrf_id)).filter(lookup).values_list("prefix", flat=True)
        ),
        key=lambda n: (n.version, n.first, n.prefixlen),
    )
    keys = [(n.version, n.first) for n in nets]
    out = {}
    for p in group:
        net = netaddr.IPNetwork(p.prefix)
        lo, hi = bisect_left(keys, (net.version, net.first)), bisect_right(keys, (net.version, net.last))
        children = [n for n in nets[lo:hi] if n.prefixlen > net.prefixlen]
        out[p.pk] = container_utilization(net, children)
    return out


def _host_values(vrf_id, group):
    blocks = _cover(group)
    hosts = defaultdict(set)
    for address in (
        IPAddress.objects.filter(_vrf_q(vrf_id)).filter(_within("address", blocks)).values_list("address", flat=True)
    ):
        address = netaddr.IPNetwork(address)  # values_list() may return str or IPNetwork
        hosts[address.version].add(int(address.ip))
    sorted_hosts = {version: sorted(values) for version, values in hosts.items()}
    ranges = [
        (netaddr.IPNetwork(start).ip, netaddr.IPNetwork(end).ip)
        for start, end in IPRange.objects.filter(_vrf_q(vrf_id), mark_utilized=True)
        .filter(_within("start_address", blocks))
        .values_list("start_address", "end_address")
    ]
    out = {}
    for p in group:
        net = netaddr.IPNetwork(p.prefix)
        inside = [
            (int(s), int(e))
            for s, e in ranges
            if s.version == net.version and net.first <= int(s) and int(e) <= net.last
        ]
        out[p.pk] = host_utilization(net, p.is_pool, sorted_hosts.get(net.version, []), inside)
    return out


def bulk_utilization(prefixes):
    """Return {prefix pk: utilization percent} with the same results as Prefix.get_utilization()."""
    result = {}
    containers, others = defaultdict(list), defaultdict(list)
    for p in prefixes:
        if p.mark_utilized:
            result[p.pk] = 100.0
        elif p.status == PrefixStatusChoices.STATUS_CONTAINER:
            containers[p.vrf_id].append(p)
        else:
            others[p.vrf_id].append(p)
    for vrf_id, group in containers.items():
        result.update(_container_values(vrf_id, group))
    for vrf_id, group in others.items():
        result.update(_host_values(vrf_id, group))
    return result
