"""Free-space computation. Pure: depends on netaddr only."""

import netaddr


def _sort_key(net):
    return (net.version, net.first, net.prefixlen)


def free_blocks(parent, children):
    """CIDR blocks of `parent` not covered by any of `children`, in address order."""
    free = netaddr.IPSet([netaddr.IPNetwork(parent)]) - netaddr.IPSet(netaddr.IPNetwork(c) for c in children)
    return sorted(free.iter_cidrs(), key=_sort_key)


def interleave(parent, children, max_gaps, with_gaps=True):
    """Merge children (network, payload) and the free blocks of `parent` in address order.

    Returns ("child", payload) and ("gap", IPNetwork) items. Gaps beyond `max_gaps` collapse into one
    trailing ("more", (count, addresses)) item.
    """
    kids = sorted(children, key=lambda c: _sort_key(netaddr.IPNetwork(c[0])))
    if not with_gaps:
        return [("child", payload) for _, payload in kids]
    gaps = free_blocks(parent, [c[0] for c in kids])
    shown, hidden = gaps[:max_gaps], gaps[max_gaps:]
    out, gi = [], 0
    for net, payload in kids:
        first = netaddr.IPNetwork(net).first
        while gi < len(shown) and shown[gi].first < first:
            out.append(("gap", shown[gi]))
            gi += 1
        out.append(("child", payload))
    out.extend(("gap", g) for g in shown[gi:])
    if hidden:
        out.append(("more", (len(hidden), sum(g.size for g in hidden))))
    return out
