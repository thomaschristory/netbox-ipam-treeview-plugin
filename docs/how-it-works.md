# How it works

The plugin is presentational: no model, no migration, no background job. Every page and fragment is built on request from `ipam.Prefix`, `ipam.Aggregate` and `ipam.VRF`.

## Lazy loading

The tree page renders the top levels only. Opening a row fetches its children as an HTML fragment and inserts it below the row, so the cost of a page is the cost of what is open, not of the whole IPAM. *Expand all*, subtree expansion, filtered trees and restoring a previous state each fetch their rows in one request, capped by `expand_all_limit`.

| Endpoint | Returns |
|---|---|
| `children/?key=...` | The direct children of one node. |
| `subtree/?key=...` | A node's whole subtree (Alt+click, `*`, *Expand all*). |
| `expand/?keys=...` | The rows needed to reopen a set of nodes. With `tab=prefix:<id>`, `aggregate:<id>` or `vrf:<id>`, rooted at that object, as on its *Tree* tab; adding `all=1` returns its whole tree (*Expand all*). |

Node keys are `vrf:<id>` (with `vrf:0` for Global), `agg:<id>@<vrf>` for an aggregate under a VRF group, and `pfx:<id>`.

Every endpoint takes `free=1` or `free=0` for free-space rows. Without it, the `ipam_tree_free` cookie written by the toolbar switch applies, then `show_free_space`.

## Nesting

For unconstrained users, children come from NetBox's cached prefix hierarchy (`_depth` and `_children`), maintained by NetBox itself on every prefix change. With constrained permissions, the tree is recomputed from the visible prefixes only (see [Permissions](permissions.md)).

Aggregates have no VRF in NetBox, so under each VRF group the plugin shows the aggregates covering that VRF's top-level prefixes. An aggregate that falls inside an open prefix (for example under `0.0.0.0/0`) is not shown as a level.

## Utilization

Utilization is computed in bulk, with a constant number of queries per VRF, instead of one call to `Prefix.get_utilization()` per row. The integration tests check that the bulk numbers equal NetBox's own for every prefix of the test data.

## Performance

- Query counts stay constant regardless of the number of rows; the integration tests guard this.
- Row rendering avoids per-row queries and per-row URL resolution.
- On the development dataset, *Expand all* of 5000 rows takes about 2 seconds on the server, plus browser layout.

## Browser side

`tree.js` is plain JavaScript with no build step: it uses `fetch()` for fragments and the browser's local storage for the open nodes (at most 200 keys, or a single flag after *Expand all*). If a fragment request is redirected to the login page because the session expired, the page reloads to the login form. If a node can no longer be loaded (for example its prefix was deleted since the page loaded), the server's error row is shown under it and its chevron turns red; collapsing and reopening the node retries.
