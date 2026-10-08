# netbox-ipam-treeview-plugin

[![ci](https://github.com/thomaschristory/netbox-ipam-treeview-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/thomaschristory/netbox-ipam-treeview-plugin/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/netbox-ipam-treeview-plugin)](https://pypi.org/project/netbox-ipam-treeview-plugin/)
[![Python](https://img.shields.io/pypi/pyversions/netbox-ipam-treeview-plugin)](https://pypi.org/project/netbox-ipam-treeview-plugin/)

A DDI-style, collapsible tree view of NetBox IPAM. Instead of a flat, paginated list of prefixes, you start
from the top-level supernets and drill down: **VRF → Aggregate → Prefix → child prefix**, with free space shown
in place, one-click **Expand all** / **Collapse all**, and the tree remembering what you had open.

![Prefix tree](https://raw.githubusercontent.com/thomaschristory/netbox-ipam-treeview-plugin/main/docs/img/tree-light.png)

## Features

- **Collapsible tree**: roots are VRFs (Global first) and the aggregates holding their prefixes; children load
  lazily as you expand, so it stays fast on large IPAMs.
- **Expand all / Collapse all** for the whole tree or any subtree (Alt+click a caret, or `*` on a focused row),
  capped by `expand_all_limit` so a click can never render an unbounded page.
- **Free space** between children, shown as greyed rows with a one-click *Create* that pre-fills the prefix and VRF.
- **Utilization bars** with the same numbers as NetBox's own prefix views, computed in bulk.
- **Row actions** (add child, edit, delete), shown only when you have the permission.
- **NetBox filters**: the native prefix filter form; matches are shown with their ancestors as greyed context.
- **Column picker**, saved per user.
- **Remembers state**: expanded nodes are restored when you come back.
- **Keyboard navigation** (treegrid pattern): ↑ ↓ move, → expand / first child, ← collapse / parent, `*` expand
  subtree, Enter opens the prefix.
- **Everywhere it is useful**: a *Prefix Tree* page, a *Tree view* button on the native prefix list (carrying
  your filters), and *Tree* tabs on Prefix, Aggregate and VRF pages. Each can be switched off.
- Light and dark themes.

## Compatibility

| Plugin | NetBox      | Python      |
|--------|-------------|-------------|
| 0.1.x  | 4.5 – 4.7   | 3.12 – 3.14 |

## Installation

```shell
source /opt/netbox/venv/bin/activate
pip install netbox-ipam-treeview-plugin
```

Add it to `configuration.py` (or `local_requirements.txt` + `plugins.py` with netbox-docker):

```python
PLUGINS = ["netbox_ipam_treeview"]
```

Then collect the static files and restart NetBox:

```shell
python /opt/netbox/netbox/manage.py collectstatic --no-input
sudo systemctl restart netbox
```

The tree lives at `/plugins/ipam-tree/` (menu: *Plugins → Prefix Tree*).

## Configuration

All settings are optional:

```python
PLUGINS_CONFIG = {
    "netbox_ipam_treeview": {
        "expand_all_limit": 5000,
    },
}
```

| Setting | Default | Meaning |
|---|---|---|
| `show_menu_item` | `True` | *Prefix Tree* entry in the plugin menu |
| `show_list_toggle` | `True` | *Tree view* button on the native prefix list |
| `show_prefix_tab` | `True` | *Tree* tab on prefix pages |
| `show_aggregate_tab` | `True` | *Tree* tab on aggregate pages |
| `show_vrf_tab` | `True` | *Tree* tab on VRF pages |
| `group_by_vrf` | `True` | Top level is one node per VRF; `False` mixes all VRFs under the aggregates (add the VRF column) |
| `show_aggregates` | `True` | Aggregates as a tree level |
| `show_free_space` | `True` | Default for free-space rows (each user can toggle it) |
| `gaps_respect_mark_utilized` | `True` | No free-space rows under pools and *mark utilized* prefixes |
| `max_gap_rows` | `64` | Free-space rows per node; the rest are summarised in one row |
| `expand_all_limit` | `5000` | Row cap for *Expand all* and filtered trees |
| `default_columns` | status, utilization, scope, VLAN, tenant, role, description, actions | Columns before a user picks their own |

## Permissions

- The page requires `ipam.view_prefix`; every row is restricted to what the user may view.
- Aggregates appear only for users with `ipam.view_aggregate`; VRF groups only for VRFs the user may view.
- With constrained (object-level) permissions, prefixes hang under their **nearest visible ancestor**, and free-space
  rows are not shown, because space taken by prefixes the user cannot see would look free.
- *Delete* links go to NetBox's own confirmation page.

## Development

The dev stack is netbox-docker with the plugin mounted live, seeded with ~8,000 RFC 1918 / ULA prefixes across
VRFs, aggregates, sites and VLANs.

```shell
make dev          # build and start NetBox on http://localhost:8000 (admin / admin)
make seed         # load the demo dataset (make reseed to wipe and reload, make seed-big for ~5x)
make test         # pure unit tests (no NetBox needed)
make test-netbox  # integration tests inside the NetBox container
make lint         # ruff
make dist         # build and check the wheel and sdist
```

## License

Apache-2.0
