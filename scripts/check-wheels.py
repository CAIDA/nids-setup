#!/usr/bin/env python3
"""Which dependencies ship binary wheels for Windows, macOS and Linux?

  scripts/check-wheels.py                     every package in the r1 environment
  scripts/check-wheels.py --release all
  scripts/check-wheels.py py-radix pytricia   named packages

Why this exists: a package with no wheel for a platform is compiled from source there,
which needs a C toolchain. macOS and Linux usually have one, so a source-only dependency
looks fine on both and then fails on a stock Windows machine -- which is exactly how
`pytricia` reached a beta tester before anyone noticed, and was replaced by `py-radix`.

Run this when ADDING a dependency to assignments/registry.toml or image/requirements.txt.
It reads the PyPI JSON API and needs no network access to any package index mirror.

What it cannot tell you: whether the package actually *works* on a platform. `pyspark`
ships no wheel but needs no compiler, and separately needs a JVM plus winutils.exe on
Windows. Wheel coverage is necessary, not sufficient.
"""

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nids_registry

PLATFORMS = {
    "windows": ("win_amd64", "win32"),
    "macos": ("macosx",),
    "linux": ("manylinux", "musllinux", "linux_"),
}
PURE = ("-py3-none-any.whl", "-py2.py3-none-any.whl")

# Source-only distributions that are nonetheless safe: no C extension, so pip needs no
# compiler and they install on any platform. Keep this list short and always give the
# reason -- an unexplained entry here silently re-admits the problem this script exists
# to catch. A package listed here can still be unusable on a platform for other reasons.
BENIGN_SOURCE_ONLY = {
    "pyspark": "pure Python plus JARs; no compiler needed. Separately needs a JVM, and "
               "on Windows winutils.exe + HADOOP_HOME -- see PLAN.md.",
}


def classify(name):
    """(version, verdict, note) for one package's latest release."""
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as fh:
            data = json.load(fh)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return "?", "LOOKUP FAILED", str(exc)

    version = data["info"]["version"]
    files = data["releases"].get(version, [])
    wheels = [f["filename"] for f in files if f["filename"].endswith(".whl")]
    has_sdist = any(f["packagetype"] == "sdist" for f in files)

    if any(tag in w for w in wheels for tag in PURE):
        return version, "pure python", "runs anywhere"
    if not wheels:
        # No wheel at all: pip builds from source wherever it is installed -- which only
        # matters if there is something to compile.
        if name in BENIGN_SOURCE_ONLY:
            return version, "source only (ok)", BENIGN_SOURCE_ONLY[name]
        return version, "SOURCE ONLY", "needs a compiler on every platform"
    missing = [plat for plat, tags in PLATFORMS.items()
               if not any(t in w for w in wheels for t in tags)]
    if missing:
        return version, "MISSING " + ",".join(missing), "compiles from source there"
    return version, "wheels: all", ("sdist fallback" if has_sdist else "wheels only")


def packages_for(release):
    """Every package the given release's environment installs."""
    assignments = nids_registry.load_assignments(
        release=None if release in (None, "all") else release)
    names = []
    for assignment in assignments.values():
        # env_for("key") is the superset: it is the assignment spec plus the key overlay.
        for pkg in assignment.env_for("key").get("extra", []):
            if pkg not in names:
                names.append(pkg)
    base = nids_registry.repo_root() / "env" / "base.txt"
    if base.exists():
        for line in base.read_text(encoding="utf-8").splitlines():
            pkg = line.split(";")[0].split("#")[0].strip()
            if pkg and pkg not in names:
                names.insert(0, pkg)
    return names


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("packages", nargs="*", help="package names (default: the release's)")
    parser.add_argument("--release", default="r1", metavar="TIER",
                        help="which release's environment to check (default: r1)")
    args = parser.parse_args(argv)

    names = args.packages or packages_for(args.release)
    print(f"{'package':<22} {'version':<10} {'wheels':<22} note")
    print("-" * 76)
    problems = 0
    for name in names:
        version, verdict, note = classify(name)
        print(f"{name:<22} {version:<10} {verdict:<22} {note}")
        if verdict.startswith(("SOURCE ONLY", "MISSING", "LOOKUP")):
            problems += 1
    if problems:
        print(f"\n{problems} package(s) will compile from source somewhere. On Windows that "
              "usually means\na failed install: there is no compiler by default. Prefer a "
              "wheel-shipping equivalent.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
