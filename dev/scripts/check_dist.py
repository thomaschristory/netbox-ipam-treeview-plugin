"""Check built distributions before a release.

Usage: python3 dev/scripts/check_dist.py DIST_DIR [--tag vX.Y.Z]

Fails when an archive contains anything outside the allowlist (for example git-excluded local
files, which hatchling does not know about), when the licence is missing from the metadata, when
the long description has a relative link (it is rendered on PyPI), or when --tag does not match
the built version.
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
import zlib
from email.parser import Parser
from pathlib import Path

NAME = "netbox_ipam_treeview_plugin"  # normalized distribution name
PACKAGE = "netbox_ipam_treeview"
PACKAGE_FILE = re.compile(rf"^{PACKAGE}/(?:[a-z_]+/)*[a-z_]+\.(?:py|html|js|css)$")
REQUIRED = {
    f"{PACKAGE}/static/{PACKAGE}/tree.js",
    f"{PACKAGE}/static/{PACKAGE}/tree.css",
    f"{PACKAGE}/templates/{PACKAGE}/tree.html",
    f"{PACKAGE}/templates/{PACKAGE}/inc/rows.html",
}
SDIST_EXTRA = {"README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml", "PKG-INFO", ".gitignore"}
RELATIVE_LINK = re.compile(r"\]\((?!https?://|#)[^)]+\)")
# {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl; no field contains a hyphen.
WHEEL_NAME = re.compile(r"^(?P<dist>[^-]+)-(?P<version>[^-]+)(?:-\d[^-]*)?-[^-]+-[^-]+-[^-]+\.whl$")


def wheel_version(name: str) -> str | None:
    """Return the version from a wheel filename of this package, or None if it is malformed."""
    match = WHEEL_NAME.match(name)
    if match is None or match["dist"] != NAME:
        return None
    return match["version"]


def check_sdist(path: Path, version: str) -> list[str]:
    problems = []
    prefix = f"{NAME}-{version}/"
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
    except (OSError, EOFError, zlib.error, tarfile.TarError) as exc:
        return [f"{path.name}: cannot read the archive: {exc}"]
    for member in members:
        if member.isdir():
            continue
        if not member.name.startswith(prefix):
            problems.append(f"{path.name}: unexpected path {member.name}")
            continue
        inner = member.name[len(prefix) :]
        if inner not in SDIST_EXTRA and not PACKAGE_FILE.match(inner):
            problems.append(f"{path.name}: not allowed: {inner}")
    return problems


def check_wheel(path: Path, version: str) -> list[str]:
    problems = []
    dist_info = f"{NAME}-{version}.dist-info/"
    allowed_info = {"METADATA", "WHEEL", "RECORD", "licenses/LICENSE", "entry_points.txt"}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            raw_metadata = archive.read(f"{dist_info}METADATA") if f"{dist_info}METADATA" in names else None
    except (OSError, EOFError, zlib.error, zipfile.BadZipFile) as exc:
        return [f"{path.name}: cannot read the archive: {exc}"]
    for name in names:
        if name.startswith(dist_info) and name[len(dist_info) :] in allowed_info:
            continue
        if not PACKAGE_FILE.match(name):
            problems.append(f"{path.name}: not allowed: {name}")
    for required in sorted(REQUIRED - set(names)):
        problems.append(f"{path.name}: missing {required}")
    if f"{dist_info}licenses/LICENSE" not in names:
        problems.append(f"{path.name}: LICENSE missing from dist-info")
    if raw_metadata is None:
        problems.append(f"{path.name}: METADATA missing from dist-info")
        return problems
    metadata = Parser().parsestr(raw_metadata.decode("utf-8", errors="replace"))
    if metadata.get("License-Expression") != "Apache-2.0":
        problems.append(f"{path.name}: License-Expression is {metadata.get('License-Expression')!r}")
    if metadata.get("License-File") != "LICENSE":
        problems.append(f"{path.name}: License-File is {metadata.get('License-File')!r}")
    for link in RELATIVE_LINK.findall(metadata.get_payload() or ""):
        problems.append(f"{path.name}: relative link in the long description: {link}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    sdists = sorted(args.dist.glob("*.tar.gz"))
    wheels = sorted(args.dist.glob("*.whl"))
    if len(sdists) != 1 or len(wheels) != 1:
        print(f"expected one sdist and one wheel in {args.dist}, found {len(sdists)} and {len(wheels)}")
        return 1
    version = wheel_version(wheels[0].name)
    if version is None:
        print(f"malformed wheel filename: {wheels[0].name} (expected {NAME}-VERSION-PYTHON-ABI-PLATFORM.whl)")
        return 1
    problems = check_sdist(sdists[0], version) + check_wheel(wheels[0], version)
    if sdists[0].name != f"{NAME}-{version}.tar.gz":
        problems.append(f"sdist and wheel versions differ: {sdists[0].name}, {wheels[0].name}")
    if args.tag is not None and args.tag != f"v{version}":
        problems.append(f"tag {args.tag} does not match the built version {version}")
    for problem in problems:
        print(problem)
    if not problems:
        print(f"ok: {sdists[0].name}, {wheels[0].name}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
