#!/usr/bin/env python3
"""Set up the NIDS assignments from one directory of cloned repositories.

  scripts/nids-setup.py discover              what is here, and what state it is in
  scripts/nids-setup.py doctor                discover, plus a reachability pass
  scripts/nids-setup.py doctor --assignment BGP

The repos come from scripts/clone-nids-repos.sh; the metadata comes from the two
registries (datasets/<id>/dataset.toml and assignments/registry.toml, documented in
datasets/SCHEMA.md).

Every subcommand here is read-only. `env`, `data`, and `verify` -- which are not read-only
-- are still to be written; see PLAN.md phase 4 and the open decisions beside it.

Root directory, in order: --root, $NIDS_ROOT, the parent of this checkout.
"""

import argparse
import pathlib
import subprocess
import sys

import nids_registry

ROLES = ("assignment", "key")


def find_root(explicit=None):
    """The parent directory holding one checkout per NIDS repository."""
    import os
    if explicit:
        return pathlib.Path(explicit).expanduser().resolve()
    if os.environ.get("NIDS_ROOT"):
        return pathlib.Path(os.environ["NIDS_ROOT"]).expanduser().resolve()
    return nids_registry.repo_root().parent


def repo_state(path):
    """One-word state for a checkout: absent, dirty, or its branch name."""
    if not path.is_dir():
        return "absent"
    if not (path / ".git").exists():
        return "not-a-repo"
    try:
        branch = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "detached"
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unreadable"
    return f"{branch}*" if dirty else branch


def env_state(path):
    """Whether a per-repo environment has been materialised yet."""
    if not path.is_dir():
        return "-"
    for candidate in (".venv", "venv", ".conda"):
        if (path / candidate).is_dir():
            return candidate
    return "none"


def manifest_source(path):
    """`nids.toml` when the repo describes itself, else the central registry."""
    return "repo" if (path / "nids.toml").exists() else "registry"


def survey(root, datasets, assignments, codes=None):
    """One row per assignment/role pair, plus any unrecognised nids-* directory."""
    rows = []
    for code, assignment in assignments.items():
        if codes and code not in codes:
            continue
        for role in ROLES:
            name = assignment.repo if role == "assignment" else assignment.key_repo
            if not name:
                continue
            path = root / name
            rows.append({
                "code": code, "role": role, "repo": name, "path": path,
                "state": repo_state(path),
                "env": env_state(path) if path.is_dir() else "-",
                "manifest": manifest_source(path) if path.is_dir() else "-",
                "status": assignment.status,
                "datasets": len(assignment.datasets),
                "check": assignment.check_notebook if role == "key" else "",
            })
    # Computed against every registered repo, not just the filtered rows -- otherwise
    # `--assignment BGP` would report every other assignment as "not in the registry".
    known = {nids_registry.repo_root().name}
    for assignment in assignments.values():
        known |= {name for name in (assignment.repo, assignment.key_repo) if name}
    unknown = sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and p.name.startswith("nids") and p.name not in known
    )
    return rows, unknown


def print_survey(root, rows, unknown, assignments, codes=None):
    print(f"root: {root}\n")
    header = f"{'code':11} {'role':10} {'repo':34} {'state':14} {'env':8} {'manifest':9} {'status'}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['code']:11} {row['role']:10} {row['repo']:34} "
              f"{row['state']:14} {row['env']:8} {row['manifest']:9} {row['status']}")

    present = sum(1 for row in rows if row["state"] not in ("absent", "not-a-repo"))
    print(f"\n{present} of {len(rows)} repositories present")

    shown = {row["code"] for row in rows}
    missing_checks = [
        code for code, a in assignments.items()
        if code in shown and a.status not in ("stub", "offsite") and not a.check_notebook
    ]
    if missing_checks:
        # DESIGN.md tracks this: for IYP it is a real gap, since it targets JupyterHub.
        print(f"no 00-environment-check.ipynb: {', '.join(missing_checks)}")

    blocked = {code: a.raw.get("blocked_on") for code, a in assignments.items()
               if a.status == "blocked" and code in shown}
    for code, why in blocked.items():
        print(f"{code} is blocked on {why}")

    if unknown:
        print(f"\nnot in the registry: {', '.join(unknown)}")
        print("  Add a block to assignments/registry.toml, or ignore if it is not an assignment.")

    if present == 0:
        print("\nNothing is cloned here yet. Run scripts/clone-nids-repos.sh --root "
              f"{root} first (it needs a GitHub token -- most nids-* repos are private).")


def cmd_discover(args):
    root = find_root(args.root)
    datasets = nids_registry.load_datasets()
    assignments = nids_registry.load_assignments()
    if not assignments:
        raise SystemExit("assignments/registry.toml is missing -- nothing to discover")
    codes = {c.upper() for c in args.assignment} if args.assignment else None
    rows, unknown = survey(root, datasets, assignments, codes)
    print_survey(root, rows, unknown, assignments, codes)
    return 0


def cmd_doctor(args):
    """discover, then hand the reachability question to the dedicated checker.

    Deliberately a subprocess rather than an import: check-datasets.py owns the exit-code
    contract and the byte-identical check runner, and duplicating either here is exactly
    the drift this tooling exists to remove.
    """
    status = cmd_discover(args)
    checker = nids_registry.repo_root() / "scripts" / "check-datasets.py"
    codes = args.assignment or [None]
    for code in codes:
        print()
        cmd = [sys.executable, str(checker)] + (["--assignment", code] if code else [])
        status |= subprocess.run(cmd).returncode
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", help="directory holding the cloned repos")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("discover", cmd_discover, "report what is cloned and what state it is in"),
        ("doctor", cmd_doctor, "discover, plus a dataset reachability pass"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--assignment", action="append", metavar="CODE",
                       help="limit to one assignment code; repeatable")
        p.set_defaults(handler=handler)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
