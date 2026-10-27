# Configuration

All settings are optional and go under `PLUGINS_CONFIG` in `configuration.py`:

```python
PLUGINS_CONFIG = {
    "netbox_ipam_treeview": {
        "expand_all_limit": 5000,
    },
}
```

## Where the tree appears

| Setting | Default | Meaning |
|---|---|---|
| `show_menu_item` | `True` | Show the *Prefix Tree* menu entry. |
| `menu_location` | `"menu"` | `"menu"`: the plugin's own *IPAM Tree* menu; `"plugins"`: the shared Plugins menu; `"ipam"`: IPAM menu, right below *Prefixes* (see below). |
| `show_list_toggle` | `True` | *Tree view* button on the native prefix list. |
| `show_prefix_tab` | `True` | *Tree* tab on prefix pages. |
| `show_aggregate_tab` | `True` | *Tree* tab on aggregate pages. |
| `show_vrf_tab` | `True` | *Tree* tab on VRF pages. |

NetBox has no plugin API to add entries to its core menus. `menu_location = "ipam"` is opt-in: the plugin patches NetBox's IPAM menu at startup to insert its entry right below *Prefixes*. This relies on NetBox internals that may change between NetBox releases; if the IPAM menu does not look as expected, the entry falls back to the plugin's own *IPAM Tree* menu.

## Tree shape

| Setting | Default | Meaning |
|---|---|---|
| `group_by_vrf` | `True` | Top level is one node per VRF. `False` mixes all VRFs under the aggregates; add the VRF column to tell them apart. |
| `show_aggregates` | `True` | Aggregates as a tree level. |

## Free space

| Setting | Default | Meaning |
|---|---|---|
| `show_free_space` | `True` | Default for free-space rows. Each user can toggle it from the toolbar. |
| `gaps_respect_mark_utilized` | `True` | No free-space rows under pools and prefixes marked *utilized*. |
| `max_gap_rows` | `64` | Free-space rows per node; the rest are summarised in one row. |

## Limits and columns

| Setting | Default | Meaning |
|---|---|---|
| `expand_all_limit` | `5000` | Row cap for *Expand all*, filtered trees and restoring a previous *Expand all*. |
| `default_columns` | status, utilization, scope, VLAN, tenant, role, description, actions | Columns shown until a user picks their own. |

`default_columns` takes the column keys as a list:

```python
"default_columns": ["status", "utilization", "scope", "vlan", "tenant", "role", "description", "actions"],
```
