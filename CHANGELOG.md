# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed

- On a *Tree* tab whose object was deleted or hidden after the page loaded, *Expand all* and the saved-state restore
  now show the *Not found or no permission* row in place of the tree instead of doing nothing (#35).

## [0.2.1] - 2026-10-27

### Fixed

- Expanding a node that no longer exists (for example a prefix deleted since the page loaded, or a stale key from
  remembered state) now shows the server's *Not found or no permission* row under it instead of only a red chevron.
  403 responses and login redirects are handled as before (#23).
- The *Tree* tabs on prefixes, aggregates and VRFs now remember which nodes were open, per object, and reopen them
  when you come back (within `expand_all_limit`), like the main page.
- The free-space switch now applies to the rows rendered with the page: with free space switched off, a freshly opened
  *Tree* tab no longer shows free-space rows. The choice is also kept in an `ipam_tree_free` cookie so the server can
  render it (#24).
- Under a VRF group, an aggregate's utilization counts only that VRF's prefixes instead of every VRF's, computed in
  one query for all aggregate rows. Without `group_by_vrf` it is still NetBox's own number (#26).

## [0.2.0] - 2026-10-27

### Added

- Documentation screenshots of the menu, free space, filters, column picker, list button and *Tree* tab.

### Changed

- **Behaviour change:** the *Prefix Tree* entry now lives in the plugin's own *IPAM Tree* menu by default
  (`menu_location = "menu"`), registered through NetBox's plugin API. Placing it right below *IPAM → Prefixes* patches
  a NetBox core menu without a supported API, so it is now opt-in: set `menu_location = "ipam"` to keep the previous
  placement. `"plugins"` (the shared Plugins menu) is unchanged. If the `"ipam"` patch does not apply, the entry now
  falls back to the plugin's own menu instead of the Plugins menu, and an unrecognised `menu_location` (e.g. `"IPAM"`)
  logs a warning and uses the own menu (it used to land in the Plugins menu) (#8).
- The tree views use NetBox's `ContentTypePermissionRequiredMixin` for `LOGIN_REQUIRED` and `ipam.view_prefix`
  checks instead of a hand-written copy, so they follow NetBox's auth handling (#9).
- NetBox 4.7.2 is now the minimum version (`min_version`). 4.7.0 and 4.7.1 recorded plaintext API tokens created
  through background bulk requests in job results, and were never tested in CI. The dev stack is pinned to 4.7.2 (#12).
- `config` is now defined unconditionally in `__init__.py`, per NetBox's plugin layout. If importing NetBox fails, the
  original error is raised instead of a missing-`config` error (#11).

### Fixed

- The *Prefix Tree* menu label, the plugin name and description, and the row-limit banner shown by `tree.js` are
  now translatable (#14).
- `tree.js` and `tree.css` URLs now carry the plugin version (`?v=`), so browsers stop running a cached script
  against new server fragments after an upgrade (#10).

## [0.1.1] - 2026-10-09

### Fixed

- The tree failed to expand (HTTP 500) when a VRF had more than 64 disjoint blocks and one IP family merged into a
  single block, e.g. a large IPv4 table next to one IPv6 supernet (#1).
- Users without `ipam.view_prefix` now get NetBox's permission-denied page instead of an empty 403 response (#2).
- Expanding a row after the session expired inserted the login page into the table; the page now reloads to the
  login form instead.
- The column picker is no longer shown to anonymous users, who cannot store column preferences.

## [0.1.0] - 2026-10-08

### Added

- Collapsible IPAM tree (VRF → Aggregate → Prefix) with lazy loading, Expand all / Collapse all and restored
  expansion state.
- Free-space rows with one-click prefix creation, bulk-computed utilization bars, permission-aware row actions.
- Native prefix filters with ancestor context, per-user column picker, keyboard navigation.
- Tree tabs on Prefix, Aggregate and VRF pages and a *Tree view* button on the prefix list, each toggleable in
  `PLUGINS_CONFIG`.
