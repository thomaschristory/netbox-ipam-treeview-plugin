"""Batched prefix utilization: a constant number of queries per VRF instead of two per prefix."""

from collections import defaultdict
from functools import reduce
from operator import or_

import netaddr
from django.db.models import Q
from ipam.choices import PrefixStatusChoices
from ipam.models import IPAddress, IPRange, Prefix

from .tree.nodes import ALL_VRFS
from .tree.usage import NetworkIndex, container_utilization, cover_blocks, host_utilization


def _vrf_q(vrf_id):
    return Q(vrf__isnull=True) if vrf_id is None else Q(vrf_id=vrf_id)


def _cover(prefixes):
    """Minimal CIDR blocks covering every prefix; each prefix lies inside exactly one of them."""
    return cover_blocks(p.prefix for p in prefixes)


def _within(field, blocks):
    return reduce(or_, (Q(**{f"{field}__net_host_contained": str(b)}) for b in blocks))


def _container_values(vrf_id, group):
    blocks = _cover(group)
    lookup = reduce(or_, (Q(prefix__net_contained_or_equal=str(b)) for b in blocks))
    index = NetworkIndex(Prefix.objects.filter(_vrf_q(vrf_id)).filter(lookup).values_list("prefix", flat=True))
    return {p.pk: container_utilization(p.prefix, index.within(p.prefix)) for p in group}


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


def bulk_aggregate_utilization(pairs):
    """Return {(aggregate pk, vrf_id): utilization percent} for (aggregate, vrf_id) pairs, in one query.

    `vrf_id` ALL_VRFS gives Aggregate.get_utilization() (prefixes of every VRF); None or a VRF pk counts only the
    prefixes of the global table or of that VRF, as shown under a VRF group of the tree.
    """
    pairs = list(pairs)
    if not pairs:
        return {}
    blocks = cover_blocks(a.prefix for a, _ in pairs)
    lookup = reduce(or_, (Q(prefix__net_contained_or_equal=str(b)) for b in blocks))
    by_vrf = defaultdict(list)
    for prefix, vrf_id in Prefix.objects.filter(lookup).values_list("prefix", "vrf_id"):
        by_vrf[vrf_id].append(prefix)
        by_vrf[ALL_VRFS].append(prefix)
    indexes = {}
    out = {}
    for agg, vrf_id in pairs:
        if vrf_id not in indexes:
            indexes[vrf_id] = NetworkIndex(by_vrf.get(vrf_id, ()))
        out[(agg.pk, vrf_id)] = container_utilization(agg.prefix, indexes[vrf_id].within(agg.prefix, or_equal=True))
    return out
