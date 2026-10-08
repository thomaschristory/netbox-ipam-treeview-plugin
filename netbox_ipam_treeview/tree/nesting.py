"""Nest CIDRs into a forest. Pure: depends on netaddr only."""

from dataclasses import dataclass
from typing import Any

import netaddr

ANY = object()  # vrf_id of items that span every VRF (aggregates)


@dataclass
class Item:
    network: Any
    payload: Any
    vrf_id: Any = None
    inclusive: bool = False  # also contains an equal network (aggregates over prefixes)


@dataclass
class Nested:
    item: Item
    depth: int
    parent: int | None  # index into the list returned by nest()


def _contains(parent: Item, child: Item) -> bool:
    p, c = parent.network, child.network
    if p.version != c.version or not (p.first <= c.first and c.last <= p.last):
        return False
    if p.prefixlen < c.prefixlen:
        return True
    return parent.inclusive and not child.inclusive and p.prefixlen == c.prefixlen


def nest(items):
    """Return items in pre-order with depth and parent index.

    Prefixes nest only inside prefixes of the same VRF; ANY-VRF items (aggregates) are always roots and
    contain prefixes of every VRF. Equal non-inclusive networks (duplicates) are siblings.
    """
    ordered = sorted(
        (Item(netaddr.IPNetwork(i.network), i.payload, i.vrf_id, i.inclusive) for i in items),
        key=lambda i: (i.network.version, i.network.first, i.network.prefixlen, 0 if i.inclusive else 1),
    )
    flat: list[Nested] = []
    stacks: dict[Any, list[int]] = {}
    current_any: int | None = None
    for item in ordered:
        idx = len(flat)
        if item.vrf_id is ANY:
            stacks, current_any = {}, idx
            flat.append(Nested(item, 0, None))
            continue
        stack = stacks.setdefault(item.vrf_id, [])
        while stack and not _contains(flat[stack[-1]].item, item):
            stack.pop()
        if stack:
            parent = stack[-1]
        elif current_any is not None and _contains(flat[current_any].item, item):
            parent = current_any
        else:
            parent = None
            if current_any is not None:  # left the aggregate: its per-VRF stacks no longer apply
                current_any, stacks = None, {item.vrf_id: stack}
        flat.append(Nested(item, 0 if parent is None else flat[parent].depth + 1, parent))
        stack.append(idx)
    return _preorder(flat)


def _preorder(flat):
    """Re-emit so every subtree is contiguous (different VRFs interleave under an aggregate)."""
    children: dict[int | None, list[int]] = {}
    for i, n in enumerate(flat):
        children.setdefault(n.parent, []).append(i)
    result: list[Nested] = []
    pending = [(i, None) for i in reversed(children.get(None, []))]
    while pending:
        i, new_parent = pending.pop()
        n = flat[i]
        result.append(Nested(n.item, n.depth, new_parent))
        here = len(result) - 1
        pending.extend((c, here) for c in reversed(children.get(i, [])))
    return result
