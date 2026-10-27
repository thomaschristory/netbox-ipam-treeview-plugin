# Development

## Repository layout

| Path | Content |
|---|---|
| `netbox_ipam_treeview/` | The plugin package. |
| `netbox_ipam_treeview/tree/` | Tree logic: free blocks, nesting, node keys, utilization math. Pure Python; the unit tests stub `netbox.plugins` (`tests/conftest.py`) so it runs without NetBox. |
| `tests/` | Unit tests (pytest), no NetBox needed. |
| `tests_netbox/` | Integration tests that run inside NetBox with `manage.py test`. |
| `dev/` | netbox-docker dev stack, the seed script and the distribution check. |
| `docs/` | This documentation, built with Zensical from `mkdocs.yml`. |
| `.github/workflows/` | CI, release and documentation workflows. |

Requirements: Python 3.12 or later, [uv](https://docs.astral.sh/uv/), Docker with the compose plugin, and `make`.

## Dev stack

The dev stack is netbox-docker with the plugin mounted live, seeded with about 8,000 RFC 1918 / ULA prefixes across VRFs, aggregates, sites and VLANs.

| Command | Effect |
|---|---|
| `make dev` | Build and start NetBox on <http://localhost:8000> (admin / admin). |
| `make seed` | Load the demo dataset. `make reseed` wipes and reloads it, `make seed-big` loads about five times more. |
| `make restart` | Restart NetBox and the worker; needed after Python changes. |
| `make down` | Stop the stack. |

Templates, JavaScript and CSS are bind-mounted, so changes to them show on a browser reload. The stack runs with `DEBUG=false` on purpose, since the debug toolbar makes requests several times slower.

## Tests and checks

| Command | Runs |
|---|---|
| `make test` | Unit tests. |
| `make test-netbox` | Integration tests inside the NetBox container. |
| `make lint` | ruff check and format check. |
| `make format` | ruff fixes and formatting. |
| `make dist` | Build the wheel and sdist and check them with twine. |
| `make docs` | Build this site into `site/`, in strict mode. |
| `make docs-serve` | Serve the site locally with live reload. |

## CI and releases

- `ci.yml` runs on pushes to `main` and on pull requests: lint, unit tests on Python 3.12 to 3.14, the package build, the documentation build, and the integration tests against NetBox.
- `release.yml` runs on a `vX.Y.Z` tag on a commit that is on `main`: it builds, checks and publishes the package to PyPI.
- `docs.yml` runs on the same tags and publishes this site to GitHub Pages. It can also be started by hand from the Actions tab.

To release: move the *Unreleased* entries of `CHANGELOG.md` under the new version, bump `netbox_ipam_treeview/version.py`, merge to `main`, then push the tag.
