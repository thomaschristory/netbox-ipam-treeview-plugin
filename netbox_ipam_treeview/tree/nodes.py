"""Tree node model and the stable string keys the browser uses to address nodes."""

import re
from dataclasses import dataclass
from typing import Any

ALL_VRFS = "*"
_KEY = re.compile(r"^(vrf|agg|pfx):(\d+)(?:@(\d+|\*))?$")


def vrf_key(vrf_id):
    return f"vrf:{vrf_id or 0}"


def agg_key(agg_id, vrf_id):
    vrf = ALL_VRFS if vrf_id == ALL_VRFS else str(vrf_id or 0)
    return f"agg:{agg_id}@{vrf}"


def pfx_key(pk):
    return f"pfx:{pk}"


def parse_key(key):
    """Return (kind, object_id, vrf_id). vrf_id None is the global table; ALL_VRFS means every VRF."""
    m = _KEY.match(key or "")
    if not m:
        raise ValueError(f"invalid node key {key!r}")
    kind, obj_id, vrf = m.group(1), int(m.group(2)), m.group(3)
    if kind == "agg":
        if vrf is None:
            raise ValueError(f"aggregate key needs a VRF part: {key!r}")
        return "aggregate", obj_id, ALL_VRFS if vrf == ALL_VRFS else (int(vrf) or None)
    if vrf is not None:
        raise ValueError(f"unexpected VRF part: {key!r}")
    if kind == "vrf":
        return "vrf", obj_id, obj_id or None
    return "prefix", obj_id, None


@dataclass
class Node:
    kind: str  # vrf | aggregate | prefix | gap | more
    key: str
    level: int
    parent_key: str | None = None
    obj: Any = None
    network: Any = None
    vrf_id: Any = None
    has_children: bool = False
    expanded: bool = False
    partial: bool = False  # expanded, but only some children were loaded (row cap reached)
    context: bool = False  # ancestor shown only to give a filtered match its place in the tree
    count: int = 0  # "more" rows: number of hidden free blocks
    addresses: int = 0  # "more" rows: total hidden addresses
    child_count: int | None = None  # descendant count; None when the user cannot see them all
    utilization: float | None = None  # filled by the view when the column is shown
    label: str = ""  # extra caption, e.g. the VRF name on aggregate rows in the aggregate tab
