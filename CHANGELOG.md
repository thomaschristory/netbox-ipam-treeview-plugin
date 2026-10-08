# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning: [SemVer](https://semver.org/).

## [0.1.0] - 2026-10-08

### Added

- Collapsible IPAM tree (VRF → Aggregate → Prefix) with lazy loading, Expand all / Collapse all and restored
  expansion state.
- Free-space rows with one-click prefix creation, bulk-computed utilization bars, permission-aware row actions.
- Native prefix filters with ancestor context, per-user column picker, keyboard navigation.
- Tree tabs on Prefix, Aggregate and VRF pages and a *Tree view* button on the prefix list, each toggleable in
  `PLUGINS_CONFIG`.
