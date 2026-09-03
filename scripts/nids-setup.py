#!/usr/bin/env python3
"""Set up the NIDS assignments from one directory of cloned repositories.

  scripts/nids-setup.py discover              what is here, and what state it is in
  scripts/nids-setup.py doctor                discover, plus a reachability pass
  scripts/nids-setup.py doctor --assignment BGP
  scripts/nids-setup.py env --release r1      one environment that runs every r1 notebook
  scripts/nids-setup.py data --release r1     stage each module's data into its data/ dir

The repos come from scripts/clone-nids-repos.sh; the metadata comes from the two
registries (datasets/<id>/dataset.toml and assignments/registry.toml, documented in
datasets/SCHEMA.md).

`discover` and `doctor` are read-only. `env` writes a generated requirements file and, unless
--dry-run, a virtual environment. `data` writes into each module's data/ directory. `verify` is
still to be written; see PLAN.md phase 4.

Module selection is the same on every subcommand: --release picks a whole tier (r1 is the
four modules that read only public data), --assignment picks individual codes, and the two
combine as an intersection. With neither, every registered module is in scope.

Root directory, in order: --root, $NIDS_ROOT, the parent of this checkout.
"""

import argparse
import gzip
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

import nids_registry

ROLES = ("assignment", "key")


def find_root(explicit=None):
    """The parent directory holding one checkout per NIDS repository."""
    if explicit:
        return pathlib.Path(explicit).expanduser().resolve()
    if os.environ.get("NIDS_ROOT"):
        return pathlib.Path(os.environ["NIDS_ROOT"]).expanduser().resolve()
    return nids_registry.repo_root().parent


def select(args):
    """(assignments, codes) for this invocation -- the one place selection is decided."""
    release = getattr(args, "release", None)
    assignments = nids_registry.load_assignments(release=release)
    if not assignments:
        if release:
            raise SystemExit(f"no modules with release = {release!r} in assignments/registry.toml")
        raise SystemExit("assignments/registry.toml is missing -- nothing to do")
    codes = None
    if getattr(args, "assignment", None):
        codes = {c.upper() for c in args.assignment}
        unknown = codes - set(assignments)
        if unknown:
            known = ", ".join(sorted(assignments))
            scope = f" in release {release}" if release else ""
            raise SystemExit(f"unknown assignment code{scope}: {', '.join(sorted(unknown))}"
                             f"\nknown: {known}")
    return assignments, codes


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
    # Unfiltered reload on purpose: `assignments` is already narrowed, and using it here
    # would report every unselected module as "not in the registry".
    known = {nids_registry.repo_root().name}
    for assignment in nids_registry.load_assignments().values():
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
    assignments, codes = select(args)
    rows, unknown = survey(root, datasets, assignments, codes)
    print_survey(root, rows, unknown, assignments, codes)
    return 0


def requirements_text(assignments, codes, label):
    """The generated requirements file: env/base.txt, then each module's extras."""
    selected = [(c, a) for c, a in assignments.items() if not codes or c in codes]
    header = [
        "# GENERATED by scripts/nids-setup.py env -- do not edit.",
        f"# selection: {label}",
        "# Sources: env/base.txt and [<CODE>.environment].extra in assignments/registry.toml.",
    ]
    for code, a in selected:
        extra = a.env_for("assignment").get("extra", [])
        header.append(f"#   {code:12} {', '.join(extra) if extra else '(base only)'}")
    base = nids_registry.base_requirements()
    extras = nids_registry.requirements_for(assignments, codes)
    return "\n".join(header + ["", "# --- base ---"] + base
                      + ["", "# --- modules ---"] + extras + [""])


def packages_in(text):
    """The requirement lines of a requirements file, without comments or blanks."""
    return [line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def venv_python(path):
    """The interpreter inside a venv, on either platform layout, or None."""
    for candidate in (path / "bin" / "python", path / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


def run_or_die(cmd, message):
    """Run a subprocess quietly; on failure print its output and exit with `message`."""
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        sys.stderr.write(done.stdout + done.stderr)
        raise SystemExit(message)


def build_venv(target, interpreter):
    """Create `target` if it is not already a venv, and return its interpreter."""
    existing = venv_python(target)
    if existing:
        print(f"reusing       {target}")
        return existing
    print(f"creating      {target} with {interpreter}")
    run_or_die(
        [interpreter, "-m", "venv", str(target)],
        # A python3.N without ensurepip is the usual cause, and "venv failed" alone
        # sends people hunting.
        f"could not create a virtual environment with {interpreter}.\n"
        "If the error mentions ensurepip, install that interpreter's python3.N-venv "
        "package or pass --python. `env --requirements-only` needs no venv at all.",
    )
    return venv_python(target)


def cmd_env(args):
    """Build one environment that runs every selected module's notebooks.

    Central rather than per-repo: the modules overlap heavily, and an instructor moving
    between them in one JupyterLab session wants one kernel, not four.
    """
    assignments, codes = select(args)
    # Registry order, not set order, so the printed list and the generated file are stable.
    selected = [c for c in assignments if not codes or c in codes]
    tier = args.release or "all"
    # The filename tracks the whole selection: a subset must not overwrite the tier's file.
    slug = tier if not codes else "-".join(selected).lower()
    label = f"{tier} / {','.join(selected)}" if codes else tier

    text = requirements_text(assignments, codes, label)
    packages = packages_in(text)
    req_path = nids_registry.repo_root() / "env" / f"requirements-{slug}.txt"

    print(f"selection:    {label}")
    print(f"modules:      {', '.join(selected)}")
    print(f"requirements: {req_path.name} ({len(packages)} packages)")

    if args.dry_run:
        print("\n" + text)
        return 0

    req_path.parent.mkdir(parents=True, exist_ok=True)
    req_path.write_text(text)
    if args.requirements_only:
        return 0

    target = (pathlib.Path(args.path).expanduser().resolve() if args.path
              else nids_registry.repo_root() / ".venv")
    print()
    python = build_venv(target, args.python or sys.executable)

    print(f"installing    {len(packages)} packages")
    run_or_die([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
               "pip could not upgrade itself")
    run_or_die([str(python), "-m", "pip", "install", "--quiet", "-r", str(req_path)],
               "pip install failed -- the output above names the package. A missing "
               "wheel for this Python version is the usual cause.")

    if args.register_kernel:
        # Writes outside this checkout, into the user's Jupyter data directory, so it is
        # opt-in rather than part of a plain `env`.
        run_or_die([str(python), "-m", "ipykernel", "install", "--user",
                    "--name", f"nids-{slug}", "--display-name", f"NIDS ({label})"],
                   "could not register the Jupyter kernel")
        print(f"kernel:       nids-{slug}")

    print(f"\nactivate with:  source {target}/bin/activate")
    if not args.register_kernel:
        print("register a Jupyter kernel for it with --register-kernel")
    return 0


def as2org_flatten(raw_path, out_path):
    """Rebuild the flattened as2org form the notebooks parse.

    publicdata serves CAIDA's raw export: `Organization` rows carrying name and country,
    and `ASN` rows carrying an asn, joined by `organizationId`. The notebooks expect one
    row per organisation with `orgName`, `country` and a `members` list -- which is what
    the in-cluster mirror holds. Staging rebuilds it so the notebooks need no change.
    """
    # Sniff rather than trust the suffix: the download lands as a .part file.
    with raw_path.open("rb") as probe:
        gzipped = probe.read(2) == b"\x1f\x8b"
    opener = gzip.open if gzipped else open
    with opener(raw_path, "rt", encoding="utf-8") as fin:
        records = [json.loads(line) for line in fin if line.strip()]
    orgs = {r["organizationId"]: r for r in records if r.get("type") == "Organization"}
    members = {}
    for record in records:
        if record.get("type") == "ASN":
            members.setdefault(record["organizationId"], []).append(record["asn"])
    with out_path.open("w", encoding="utf-8") as fout:
        for org_id, asns in members.items():
            org = orgs.get(org_id, {})
            fout.write(json.dumps({"orgName": org.get("name", ""),
                                   "country": org.get("country", ""),
                                   "members": asns}) + "\n")
    return sum(len(a) for a in members.values())


TRANSFORMS = {"as2org-flatten": as2org_flatten}


def stage_one(dataset, pins, dest_dir, source, force=False):
    """Put one dataset into dest_dir. Returns a one-line status."""
    name = dataset.staged_name(**pins)
    target = dest_dir / name
    if target.exists() and not force:
        return f"{name}  present"

    url = dataset.mirror_url(**pins) if source == "nrp" else dataset.url(**pins)
    transform = dataset.stage.get("transform")
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Download beside the target, then move into place, so an interrupted run never
    # leaves a half-file that the next run reports as `present`.
    scratch = target.with_suffix(target.suffix + ".part")
    try:
        urllib.request.urlretrieve(url, scratch)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        scratch.unlink(missing_ok=True)
        hint = ""
        if source == "nrp":
            hint = " (the mirror resolves only inside the NRP cluster)"
        return f"{name}  FAILED: {exc}{hint}"

    if transform and source != "nrp":
        # The mirror already holds the transformed form; only the public file needs it.
        if transform not in TRANSFORMS:
            scratch.unlink(missing_ok=True)
            return f"{name}  FAILED: unknown transform {transform!r}"
        try:
            count = TRANSFORMS[transform](scratch, target)
        except (OSError, ValueError, KeyError) as exc:
            scratch.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            return f"{name}  FAILED: {transform}: {exc}"
        scratch.unlink(missing_ok=True)
        return f"{name}  built from {url.rsplit('/', 1)[-1]} ({count} ASNs)"

    scratch.replace(target)
    return f"{name}  {target.stat().st_size / 1e6:.1f} MB"


def cmd_data(args):
    """Stage each selected module's datasets into that module's own data/ directory.

    Per repo rather than a shared cache because the notebooks use relative paths --
    `Path("data/as2org.jsonl")` -- so this is what makes a staged file visible to them.
    """
    root = find_root(args.root)
    datasets = nids_registry.load_datasets()
    assignments, codes = select(args)
    source = "nrp" if args.nrp else "local"

    print(f"root:   {root}")
    print(f"source: {source}"
          f"{'  (in-cluster mirror)' if source == 'nrp' else '  (publicdata / open web)'}\n")

    staged = failed = 0
    for code, assignment in assignments.items():
        if codes and code not in codes:
            continue
        repo = root / assignment.repo if assignment.repo else None
        wanted = [(datasets[e["id"]], assignment.pins_for(e["id"]))
                  for e in assignment.datasets
                  if e["id"] in datasets and datasets[e["id"]].stage]
        if not wanted:
            continue
        print(f"{code}")
        if repo is None or not repo.is_dir():
            print(f"  skipped -- {assignment.repo} is not cloned under {root}")
            continue
        for dataset, pins in wanted:
            if code not in dataset.stage.get("into", [code]):
                continue
            line = stage_one(dataset, pins, repo / "data", source, args.force)
            print(f"  {line}")
            if "FAILED" in line:
                failed += 1
            else:
                staged += 1
        print()

    print(f"{staged} staged, {failed} failed")
    if failed:
        print("Nothing else fetches these -- the notebook will try its own download and "
              "hit the same error.")
    return 1 if failed else 0


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
        ("env", cmd_env, "build one environment that runs the selected modules"),
        ("data", cmd_data, "stage each module's datasets into its own data/ directory"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--assignment", action="append", metavar="CODE",
                       help="limit to one assignment code; repeatable")
        p.add_argument("--release", metavar="TIER",
                       help="limit to a release tier, e.g. r1 (default: every module)")
        p.set_defaults(handler=handler)
        if name == "data":
            p.add_argument("--nrp", action="store_true",
                           help="fetch from the in-cluster mirror instead of the open web")
            p.add_argument("--force", action="store_true",
                           help="restage files that are already present")
        if name != "env":
            continue
        p.add_argument("--path", metavar="DIR",
                       help="where the environment goes (default: <nids-setup>/.venv)")
        p.add_argument("--python", metavar="EXE",
                       help="interpreter to build it with (default: the one running this)")
        p.add_argument("--requirements-only", action="store_true",
                       help="write env/requirements-<tier>.txt and stop")
        p.add_argument("--register-kernel", action="store_true",
                       help="also install a Jupyter kernel (writes to your Jupyter data dir)")
        p.add_argument("--dry-run", action="store_true",
                       help="print the requirements file, write nothing")

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
