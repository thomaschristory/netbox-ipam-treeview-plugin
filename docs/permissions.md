# Permissions

The plugin has no permissions of its own; it uses NetBox's object permissions.

| Object | Permission | Effect |
|---|---|---|
| Prefix | `ipam.view_prefix` | Required for the tree page. Without it, NetBox's permission-denied page is shown. |
| Aggregate | `ipam.view_aggregate` | Aggregates appear as a tree level only for users who have it. |
| VRF | `ipam.view_vrf` | VRF groups appear only for VRFs the user may view. |
| Prefix | `ipam.add_prefix`, `change_prefix`, `delete_prefix` | Show the matching row actions and the *Create* link on free-space rows. |

Every row is restricted to what the user may view. *Delete* links go to NetBox's own confirmation page.

## Constrained permissions

With object-level constraints on `view_prefix` (for example, only prefixes of one tenant), the tree changes behaviour so that it does not leak prefixes the user cannot see:

- Prefixes hang under their **nearest visible ancestor**, instead of under a parent that is hidden.
- **Free-space rows are not shown**, because space taken by hidden prefixes would look free.
- The *Children* column is empty, since NetBox's cached child counts include hidden prefixes.
- Expand carets are computed from the visible prefixes only.
- Aggregate utilization counts only the visible prefixes, so it can differ from the number on the aggregate's own NetBox page.

Users with an unconstrained `view_prefix` get the faster path that uses NetBox's cached prefix depth and child counts.
