"""Turns permission-restricted IPAM querysets into ordered tree Node lists."""

import netaddr
from django.db.models import Exists, OuterRef
from ipam.models import VRF, Aggregate, Prefix

from ..conf import get_setting
from .gaps import interleave
from .nesting import ANY, Item, nest
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
            child_count=None if self.restricted else p._children,
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
        # With constrained permissions, prefixes the user cannot see would be presented as free space.
        if not self.show_free_space or self.restricted:
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
        return self._prune_hidden_children(sorted(nodes, key=_net_key))

    def _prune_hidden_children(self, nodes):
        """With constrained permissions, drop the expand toggle from prefixes whose descendants are all hidden.

        NetBox's cached _children counts every descendant, visible or not.
        """
        if not self.restricted:
            return nodes
        pending = [n for n in nodes if n.kind == "prefix" and n.has_children and not n.expanded]
        if not pending:
            return nodes
        visible = Prefix.objects.restrict(self.user, "view")
        has_visible = set()
        for is_global in (True, False):
            group = [n.obj.pk for n in pending if (n.vrf_id is None) == is_global]
            if not group:
                continue
            inner = visible.filter(prefix__net_contained=OuterRef("prefix"))
            inner = inner.filter(vrf__isnull=True) if is_global else inner.filter(vrf_id=OuterRef("vrf_id"))
            has_visible |= set(Prefix.objects.filter(pk__in=group).filter(Exists(inner)).values_list("pk", flat=True))
        for n in pending:
            n.has_children = n.obj.pk in has_visible
        return nodes

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
            return self._with_gaps(agg, key, self._prune_hidden_children(kids), level + 1, vrf_id)
        p = self._get_prefix(obj_id)
        kids = [self._prefix_node(c, level + 1, key) for c in self._direct_children(p)]
        return self._with_gaps(p, key, self._prune_hidden_children(kids), level + 1, p.vrf_id)

    def node_for(self, obj):
        if isinstance(obj, Prefix):
            return self._prune_hidden_children([self._prefix_node(obj, 0, None)])[0]
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

    # --- bulk loading ----------------------------------------------------------------------------------------

    def _emit(self, nested, *, level, parent_key, parent_obj, vrf_id, gaps, matches=None):
        """Turn nest() output into Nodes in display order, children of each loaded parent marked expanded.

        `matches` (filtered mode) is the set of matching prefix pks; every other node is a context row.
        """
        children: dict[int | None, list[int]] = {}
        for i, n in enumerate(nested):
            children.setdefault(n.parent, []).append(i)
        out = []

        def make(i, lvl, pkey):
            kind, obj, vid = nested[i].item.payload
            is_agg = kind == "aggregate"
            node = self._agg_node(obj, vid, lvl, pkey) if is_agg else self._prefix_node(obj, lvl, pkey)
            if matches is not None:
                node.context = not (kind == "prefix" and obj.pk in matches)
            return node

        def walk(indexes, lvl, pkey, pobj, vid):
            nodes = [make(i, lvl, pkey) for i in indexes]
            index_of = {id(node): i for node, i in zip(nodes, indexes, strict=True)}
            seq = self._with_gaps(pobj, pkey, nodes, lvl, vid) if gaps and pobj is not None else nodes
            for node in seq:
                out.append(node)
                i = index_of.get(id(node))
                if i is not None and i in children:
                    node.expanded = True
                    walk(children[i], lvl + 1, node.key, nested[i].item.payload[1], node.vrf_id)

        walk(children.get(None, []), level, parent_key, parent_obj, vrf_id)
        return out

    def _aggregate_items(self, vrf_id):
        if self.aggregates is None:
            return []
        return [Item(a.prefix, ("aggregate", a, vrf_id), ANY, inclusive=True) for a in self.aggregates]

    @staticmethod
    def _drop_empty_aggregates(nested):
        parents = {n.parent for n in nested if n.parent is not None}
        keep = [n.item for i, n in enumerate(nested) if n.item.payload[0] != "aggregate" or i in parents]
        return nest(keep)

    def subtree(self, key, level):
        """Every visible descendant of `key` (capped at limit), in display order."""
        kind, obj_id, vrf_id = self._parse(key)
        if kind == "prefix":
            obj = self._get_prefix(obj_id)
            vrf_id = obj.vrf_id
            qs = self.prefixes.filter(vrf_id=obj.vrf_id, prefix__net_contained=str(obj.prefix))
        elif kind == "aggregate":
            self._check_vrf(vrf_id)
            obj = self._get_aggregate(obj_id)
            qs = self._in_vrf(self.prefixes, vrf_id).filter(prefix__net_contained_or_equal=str(obj.prefix))
        else:
            self._check_vrf(vrf_id)
            obj = None
            qs = self._in_vrf(self.prefixes, vrf_id)
        rows = list(qs.order_by("prefix")[: self.limit + 1])
        if len(rows) > self.limit:
            self.truncated = True
            rows = rows[: self.limit]
        items = [Item(p.prefix, ("prefix", p, p.vrf_id), p.vrf_id) for p in rows]
        if kind == "vrf":
            items += self._aggregate_items(vrf_id)
        nested = self._drop_empty_aggregates(nest(items))
        # Free space is only shown when every child is loaded; a truncated load would show hidden children as free.
        nodes = self._emit(
            nested, level=level + 1, parent_key=key, parent_obj=obj, vrf_id=vrf_id, gaps=not self.truncated
        )
        return self._prune_hidden_children(nodes)

    def full_tree(self):
        """Roots plus every root's subtree, sharing one row budget."""
        out, budget, limit = [], self.limit, self.limit
        for root in self.roots():
            out.append(root)
            if not root.has_children:
                continue
            if budget <= 0:
                self.truncated = True
                continue
            self.limit = budget
            sub = self.subtree(root.key, root.level)
            budget -= sum(n.kind in ("prefix", "aggregate") for n in sub)
            root.expanded = bool(sub)
            out.extend(sub)
        self.limit = limit
        return out

    def expand(self, keys):
        """Roots, with every node whose key is in `keys` expanded (restores a saved expansion state)."""
        keys = set(list(keys)[:500])
        out = []

        def visit(nodes):
            for node in nodes:
                if len(out) >= self.limit:
                    self.truncated = True
                    return
                out.append(node)
                if node.has_children and node.key in keys:
                    try:
                        kids = self.children(node.key, node.level)
                    except NodeNotFound:
                        continue
                    node.expanded = True
                    visit(kids)

        visit(self.roots())
        return out

    def filtered(self, match_qs):
        """Matching prefixes with their ancestors as greyed context rows, fully expanded, no free space."""
        rows = list(self.prefixes.filter(pk__in=match_qs.order_by().values("pk")).order_by("prefix")[: self.limit + 1])
        self.truncated = len(rows) > self.limit
        rows = rows[: self.limit]
        if not rows:
            return []
        matches = {p.pk for p in rows}
        vrf_ids = {p.vrf_id for p in rows}
        candidates = [
            p for v in vrf_ids for p in self._in_vrf(self.prefixes, v).filter(_children__gt=0).exclude(pk__in=matches)
        ]
        nested = nest(Item(p.prefix, ("prefix", p, p.vrf_id), p.vrf_id) for p in rows + candidates)
        keep = set()
        for i, n in enumerate(nested):
            j = i if n.item.payload[1].pk in matches else None
            while j is not None and j not in keep:
                keep.add(j)
                j = nested[j].parent
        kept = [nested[i].item.payload[1] for i in sorted(keep)]

        if not self.group_by_vrf:
            items = [Item(p.prefix, ("prefix", p, p.vrf_id), p.vrf_id) for p in kept]
            nested = self._drop_empty_aggregates(nest(items + self._aggregate_items(ALL_VRFS)))
            nodes = self._emit(
                nested, level=0, parent_key=None, parent_obj=None, vrf_id=ALL_VRFS, gaps=False, matches=matches
            )
            return self._prune_hidden_children(nodes)

        out = []
        groups: dict = {}
        visible_vrfs = set(self.vrfs.values_list("pk", flat=True))
        for p in kept:
            # Same rule as roots(): prefixes in a VRF the user cannot view are not reachable in grouped mode.
            if p.vrf_id is None or p.vrf_id in visible_vrfs:
                groups.setdefault(p.vrf_id, []).append(p)
        for vrf_id in sorted(groups, key=lambda v: (v is not None, groups[v][0].vrf.name if v else "")):
            prefixes = groups[vrf_id]
            vrf_node = Node(
                "vrf",
                vrf_key(vrf_id),
                0,
                obj=prefixes[0].vrf,
                vrf_id=vrf_id,
                has_children=True,
                expanded=True,
                context=True,
            )
            out.append(vrf_node)
            items = [Item(p.prefix, ("prefix", p, p.vrf_id), p.vrf_id) for p in prefixes]
            nested = self._drop_empty_aggregates(nest(items + self._aggregate_items(vrf_id)))
            out += self._emit(
                nested, level=1, parent_key=vrf_node.key, parent_obj=None, vrf_id=vrf_id, gaps=False, matches=matches
            )
        return self._prune_hidden_children(out)
