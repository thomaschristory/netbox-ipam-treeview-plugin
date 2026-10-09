# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning: [SemVer](https://semver.org/).

## [Unreleased]

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
