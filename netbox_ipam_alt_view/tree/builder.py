"""Turns permission-restricted IPAM querysets into ordered tree Node lists."""

import netaddr
from ipam.models import VRF, Aggregate, Prefix

from ..conf import get_setting
from .gaps import interleave
from .nesting import Item, nest
from .nodes import ALL_VRFS, Node, agg_key, parse_key, pfx_key, vrf_key


class NodeNotFound(Exception):
    pass


def _net_key(node):
    net = netaddr.IPNetwork(node.network)
    return (net.version, net.first, net.prefixlen, 0 if node.kind == "aggregate" else 1)


class TreeBuilder:
    def __init__(
        self,
        user,
        *,
        show_free_space=None,
        group_by_vrf=None,
        show_aggregates=None,
        limit=None,
        max_gap_rows=None,
        respect_mark_utilized=None,
    ):
        def opt(value, key):
            return get_setting(key) if value is None else value

        self.user = user
        self.show_free_space = opt(show_free_space, "show_free_space")
        self.group_by_vrf = opt(group_by_vrf, "group_by_vrf")
        self.limit = opt(limit, "expand_all_limit")
        self.max_gap_rows = opt(max_gap_rows, "max_gap_rows")
        self.respect_mark_utilized = opt(respect_mark_utilized, "gaps_respect_mark_utilized")
        visible = Prefix.objects.restrict(user, "view")
        # restrict() only adds a WHERE clause for constrained permissions. Unconstrained users can rely on
        # NetBox's cached _depth; constrained users need nearest-visible-ancestor nesting instead.
        self.restricted = bool(visible.query.where)
        self.prefixes = visible.select_related("vrf", "tenant", "role", "vlan").prefetch_related("scope")
        self.aggregates = None
        if opt(show_aggregates, "show_aggregates") and user.has_perm("ipam.view_aggregate"):
            self.aggregates = Aggregate.objects.restrict(user, "view").select_related("rir")
        self.vrfs = VRF.objects.restrict(user, "view")
        self.truncated = False

    # --- helpers ---------------------------------------------------------------------------------------------

    def _in_vrf(self, qs, vrf_id):
        if vrf_id == ALL_VRFS:
            return qs
        return qs.filter(vrf__isnull=True) if vrf_id is None else qs.filter(vrf_id=vrf_id)

    def _prefix_node(self, p, level, parent_key):
        return Node(
            "prefix",
            pfx_key(p.pk),
            level,
            parent_key,
            obj=p,
            network=p.prefix,
            vrf_id=p.vrf_id,
            has_children=p._children > 0,
        )

    def _agg_node(self, agg, vrf_id, level, parent_key):
        return Node(
            "aggregate",
            agg_key(agg.pk, vrf_id),
            level,
            parent_key,
            obj=agg,
            network=agg.prefix,
            vrf_id=vrf_id,
            has_children=True,
        )

    def _gaps_allowed(self, obj):
        if not self.show_free_space:
            return False
        return not (self.respect_mark_utilized and isinstance(obj, Prefix) and (obj.is_pool or obj.mark_utilized))

    def _with_gaps(self, parent_obj, parent_key, child_nodes, level, vrf_id):
        items = interleave(
            parent_obj.prefix,
            [(n.network, n) for n in child_nodes],
            self.max_gap_rows,
            with_gaps=self._gaps_allowed(parent_obj),
        )
        out = []
        for kind, payload in items:
            if kind == "child":
                out.append(payload)
            elif kind == "gap":
                key = f"gap:{payload}@{vrf_id or 0}"
                out.append(Node("gap", key, level, parent_key, network=payload, vrf_id=vrf_id))
            else:
                count, addresses = payload
                out.append(Node("more", f"more:{parent_key}", level, parent_key, count=count, addresses=addresses))
        return out

    def _top_prefixes(self, vrf_id):
        """Visible prefixes with no visible ancestor in their VRF, as (pk, network, vrf_id)."""
        qs = self._in_vrf(self.prefixes, vrf_id)
        if not self.restricted:
            return list(qs.filter(_depth=0).values_list("pk", "prefix", "vrf_id"))
        rows = list(qs.values_list("pk", "prefix", "vrf_id"))
        return [n.item.payload for n in nest(Item(r[1], r, r[2]) for r in rows) if n.parent is None]

    def _direct_children(self, p):
        """Visible prefixes whose nearest visible ancestor is p."""
        qs = self.prefixes.filter(vrf_id=p.vrf_id, prefix__net_contained=str(p.prefix))
        if not self.restricted:
            return list(qs.filter(_depth=p._depth + 1))
        rows = list(qs.values_list("pk", "prefix"))
        top = [n.item.payload[0] for n in nest(Item(r[1], r, p.vrf_id) for r in rows) if n.parent is None]
        return list(self.prefixes.filter(pk__in=top))

    def _top_level(self, vrf_id, level, parent_key):
        tops = self._top_prefixes(vrf_id)
        aggs = list(self.aggregates) if self.aggregates is not None else []
        used, orphans = set(), []
        for pk, net, _vrf in tops:
            agg = next((a for a in aggs if net in a.prefix), None)
            if agg is None:
                orphans.append(pk)
            else:
                used.add(agg.pk)
        nodes = [self._agg_node(a, vrf_id, level, parent_key) for a in aggs if a.pk in used]
        nodes += [self._prefix_node(p, level, parent_key) for p in self.prefixes.filter(pk__in=orphans)]
        return sorted(nodes, key=_net_key)

    def _get_prefix(self, pk):
        try:
            return self.prefixes.get(pk=pk)
        except Prefix.DoesNotExist:
            raise NodeNotFound(pk) from None

    def _get_aggregate(self, pk):
        if self.aggregates is None:
            raise NodeNotFound(pk)
        try:
            return self.aggregates.get(pk=pk)
        except Aggregate.DoesNotExist:
            raise NodeNotFound(pk) from None

    def _check_vrf(self, vrf_id):
        if vrf_id is not None and vrf_id != ALL_VRFS and not self.vrfs.filter(pk=vrf_id).exists():
            raise NodeNotFound(vrf_id)

    def _parse(self, key):
        try:
            return parse_key(key)
        except ValueError:
            raise NodeNotFound(key) from None

    # --- public API ------------------------------------------------------------------------------------------

    def roots(self):
        if not self.group_by_vrf:
            return self._top_level(ALL_VRFS, 0, None)
        vrf_ids = set(self.prefixes.order_by().values_list("vrf_id", flat=True).distinct())
        nodes = []
        if None in vrf_ids:
            nodes.append(Node("vrf", vrf_key(None), 0, has_children=True))
        for vrf in self.vrfs.filter(pk__in=vrf_ids - {None}).order_by("name"):
            nodes.append(Node("vrf", vrf_key(vrf.pk), 0, obj=vrf, vrf_id=vrf.pk, has_children=True))
        return nodes

    def children(self, key, level):
        kind, obj_id, vrf_id = self._parse(key)
        if kind == "vrf":
            self._check_vrf(vrf_id)
            return self._top_level(vrf_id, level + 1, key)
        if kind == "aggregate":
            self._check_vrf(vrf_id)
            agg = self._get_aggregate(obj_id)
            tops = [pk for pk, net, _ in self._top_prefixes(vrf_id) if net in agg.prefix]
            kids = sorted(
                (self._prefix_node(p, level + 1, key) for p in self.prefixes.filter(pk__in=tops)), key=_net_key
            )
            return self._with_gaps(agg, key, kids, level + 1, vrf_id)
        p = self._get_prefix(obj_id)
        kids = [self._prefix_node(c, level + 1, key) for c in self._direct_children(p)]
        return self._with_gaps(p, key, kids, level + 1, p.vrf_id)

    def node_for(self, obj):
        if isinstance(obj, Prefix):
            return self._prefix_node(obj, 0, None)
        return Node("vrf", vrf_key(obj.pk), 0, obj=obj, vrf_id=obj.pk, has_children=True)

    def aggregate_roots(self, agg):
        vrf_ids = set(
            self.prefixes.filter(prefix__net_contained_or_equal=str(agg.prefix))
            .order_by()
            .values_list("vrf_id", flat=True)
            .distinct()
        )
        names = dict(self.vrfs.filter(pk__in=vrf_ids - {None}).values_list("pk", "name"))
        order = ([None] if None in vrf_ids else []) + sorted((v for v in vrf_ids if v in names), key=names.get)
        nodes = []
        for v in order:
            node = self._agg_node(agg, v, 0, None)
            node.label = names.get(v, "Global")
            nodes.append(node)
        return nodes
