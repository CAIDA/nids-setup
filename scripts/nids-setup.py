#!/usr/bin/env python3
"""Set up the NIDS assignments from one directory of cloned repositories.

  scripts/nids-setup.py discover              what is here, and what state it is in
  scripts/nids-setup.py doctor                discover, plus a reachability pass
  scripts/nids-setup.py doctor --assignment BGP
  scripts/nids-setup.py env --release r1      one environment that runs every r1 notebook
  scripts/nids-setup.py data --release r1     stage each module's data into its data/ dir
  scripts/nids-setup.py verify --release r1   run the key notebooks; what is ready to hand out

The repos come from scripts/clone-nids-repos.sh; the metadata comes from the two
registries (datasets/<id>/dataset.toml and assignments/registry.toml, documented in
datasets/SCHEMA.md).

`discover` and `doctor` are read-only. `env` writes a generated requirements file and, unless
--dry-run, a virtual environment. `data` writes into each module's data/ directory. `verify`
executes notebooks but saves nothing -- it needs the -key repos, which are private, so it is an
instructor-side command.

Module selection is the same on every subcommand: --release picks a whole tier (r1 is the
four modules that read only public data), --assignment picks individual codes, and the two
combine as an intersection. With neither, every registered module is in scope.

Root directory, in order: --root, $NIDS_ROOT, the parent of this checkout.
"""

import argparse
import concurrent.futures
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        ).stdout.strip() or "detached"
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
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
    root = find_root(getattr(args, "root", None))
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


def activate_hint(target):
    """The line a user types to activate `target`, in their platform's shell."""
    if os.name == "nt":
        # Activate.ps1, not activate.bat: PowerShell resolves the bare name to the .bat,
        # which sets its variables in a child cmd process and so silently does nothing.
        return f"{target}\\Scripts\\Activate.ps1"
    return f"source {target}/bin/activate"


def venv_python(path):
    """The interpreter inside a venv, on either platform layout, or None."""
    for candidate in (path / "bin" / "python", path / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


def run_or_die(cmd, message):
    """Run a subprocess quietly; on failure print its output and exit with `message`."""
    done = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
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
    req_path.write_text(text, encoding="utf-8", newline="\n")
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

    print(f"\nactivate with:  {activate_hint(target)}")
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
    with out_path.open("w", encoding="utf-8", newline="\n") as fout:
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
    root = find_root(getattr(args, "root", None))
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


# --- verify ------------------------------------------------------------------------
# The acceptance gate: one command answering "which modules are ready to hand out".
# Instructor-side by construction -- what it runs lives in the private -key repos, so a
# student running this correctly finds nothing to run (D3).

# Run inside the built environment, not this interpreter, because that is the
# environment the notebook will actually run in -- verifying anything else verifies the
# wrong thing. Kept as source text rather than a file next to this one so `verify` stays
# a single-file change; it is passed to `python -c`.
NOTEBOOK_RUNNER = r'''
import json, re, sys
import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

path, timeout = sys.argv[1], int(sys.argv[2])
nb = nbformat.read(path, as_version=4)
# resources.metadata.path is the notebook's working directory. The notebooks use
# relative paths -- Path("data/as2org.jsonl") -- so this is what makes staged data
# visible to them.
client = NotebookClient(nb, timeout=timeout, resources={"metadata": {"path": "."}})
result = {"cells": sum(1 for c in nb.cells if c.cell_type == "code"), "lines": [],
          "error": None, "kernel": None}
# IPython colours tracebacks; this report is plain text and read in logs.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
try:
    client.execute()
except CellExecutionError as exc:
    # The last line is the exception itself. The frames above it are about the
    # notebook's own code, which the person running verify is about to open anyway.
    result["error"] = ANSI.sub("", str(exc)).strip().splitlines()[-1]
except Exception as exc:
    result["error"] = ANSI.sub("", f"{exc.__class__.__name__}: {exc}")
# Which interpreter the kernel actually ran in. Jupyter resolves the kernelspec by name
# through its own search path, where a *user* kernelspec outranks this environment's --
# so "we launched the venv's python" does not by itself prove the notebook ran there.
# jupyter_client substitutes sys.executable for a bare "python"/"pythonN" argv[0], which
# is what this environment's own spec holds; anything else is a real answer to report.
# Resolved from the kernelspec directly rather than from the client, which drops its
# kernel manager once execution finishes -- reading it there returns None and the check
# silently never fires.
try:
    from jupyter_client.kernelspec import KernelSpecManager
    name = nb.metadata.get("kernelspec", {}).get("name") or "python3"
    argv0 = KernelSpecManager().get_kernel_spec(name).argv[0]
    bare = ("python", "python3", "python%i" % sys.version_info[0],
            "python%i.%i" % sys.version_info[:2])
    result["kernel"] = sys.executable if argv0 in bare else argv0
except Exception:
    pass
# The shared check runner prints "[ ok ] ...", "[FAIL] ...", "[warn] ..."; collect those
# from whatever ran, including the cells before a failure.
for cell in nb.cells:
    for output in cell.get("outputs", []):
        text = output.get("text") or ""
        for line in text.splitlines():
            if line.startswith(("[ ok ]", "[FAIL]", "[warn]")):
                result["lines"].append(line.rstrip())
print("\n__NIDS_VERIFY__" + json.dumps(result))
'''


def printable(text):
    """Make one line of notebook output safe for whatever console this is.

    A notebook can print anything; a console cannot print anything -- the encoder is
    cp1252 on Windows and ascii under `LC_ALL=C`, and one unencodable character in a
    captured line would abort the whole run with UnicodeEncodeError. Same locale-encoding
    class as the file I/O fixed on 2026-09-04, one layer further out: this is the only
    text here that does not come from the registry, so it is the only text that needs it.
    """
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, "replace").decode(encoding, "replace")


def check_target(assignment, key_path):
    """Which notebook `verify` should run for one module, and why.

    Returns (path, kind, note). The registry names a `check` notebook per module, but for
    every release-1 module that notebook is either declared absent (IYP, D8) or named and
    not actually in the repo [verified 2026-09-04 -- ASN and BGP key repos have never held
    one, on any branch]. Falling back to the module's own key notebook is what keeps this
    command from being inert for the whole release: running it end to end is the check
    that caught the BGP key's missing `import pandas as pd`.
    """
    named = assignment.check_notebook
    if named:
        candidate = key_path / named
        if candidate.exists():
            return candidate, "check", ""
        note = f"registry names {named}, which is not in the repo"
    else:
        note = "module ships no environment check"
    fallback = key_path / f"{key_path.name}.ipynb"
    if fallback.exists():
        return fallback, "notebook", note
    return None, "none", note


def run_notebook(python, notebook, timeout):
    """Execute one notebook headlessly in `python`'s environment. Returns the runner's dict.

    Nothing is written back: the executed copy stays in memory, so a `-key` checkout is
    the same after this as before it.
    """
    done = subprocess.run(
        [str(python), "-c", NOTEBOOK_RUNNER, notebook.name, str(timeout)],
        cwd=str(notebook.parent), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    for line in done.stdout.splitlines():
        if line.startswith("__NIDS_VERIFY__"):
            return json.loads(line[len("__NIDS_VERIFY__"):])
    # The runner itself did not get far enough to report -- a missing nbclient, or the
    # interpreter failing to start. Its own stderr is the only useful thing here.
    tail = (done.stderr or done.stdout).strip().splitlines()
    return {"cells": 0, "lines": [], "kernel": None,
            "error": tail[-1] if tail else f"the notebook runner exited {done.returncode}"}


def cmd_verify(args):
    """Run each selected module's key notebook and report which modules are ready.

    Serial on purpose: these notebooks parse multi-hundred-megabyte RIBs, and running four
    of them at once turns a memory limit into a confusing failure.
    """
    root = find_root(getattr(args, "root", None))
    assignments, codes = select(args)
    tier = args.release or "all"

    venv = pathlib.Path(args.path).expanduser().resolve() if args.path \
        else nids_registry.repo_root() / ".venv"
    # Absolute either way: the notebook runs with its own repo as the working directory,
    # so a relative interpreter path -- or a bare name found on PATH -- would not resolve
    # there. shutil.which handles both forms.
    python = pathlib.Path(shutil.which(args.python) or args.python).resolve() \
        if args.python else venv_python(venv)
    if python is None:
        # sys.executable would run the notebooks in whatever interpreter launched this,
        # which is not the environment `env` built and not what a module will use.
        raise SystemExit(
            f"no environment at {venv} -- run `nids-setup.py env --release {tier}` first, "
            "or pass --python to name an interpreter that has the modules' packages.")

    print(f"root:    {root}")
    print(f"python:  {python}")
    print(f"timeout: {args.timeout}s per notebook\n")

    results = []
    for code, assignment in assignments.items():
        if codes and code not in codes:
            continue
        if not assignment.key_repo:
            results.append((code, "warn", "no key repo in the registry"))
            continue
        key_path = root / assignment.key_repo
        if not key_path.is_dir():
            # Expected for a student, and for anyone without org access: the key repos are
            # private. Never a failure -- D3.
            results.append((code, "warn", f"{assignment.key_repo} is not cloned under {root}"))
            continue
        notebook, kind, note = check_target(assignment, key_path)
        if notebook is None:
            results.append((code, "warn", f"no check available -- {note}"))
            continue

        label = f"{notebook.parent.name}/{notebook.name}"
        if args.dry_run:
            results.append((code, "skip", f"would run {label}"))
            continue

        print(printable(f"{code}: running {label}"
                        + (f"  ({kind}; {note})" if note else f"  ({kind})")))
        outcome = run_notebook(python, notebook, args.timeout)
        ran_in = outcome.get("kernel")
        if ran_in and pathlib.Path(ran_in) != python:
            # Not fatal -- the notebook may well pass -- but it means this run did not
            # test the environment it was asked to test, which is the whole point.
            print(f"  [warn] the kernel ran in {ran_in}, not {python}")
        for line in outcome["lines"]:
            print(f"  {printable(line)}")
        # A check notebook's runner *swallows* the exception and prints "[FAIL]" -- it is
        # built that way so the remaining checks still run. So executing to the end is not
        # the same as passing, and reading only the exception would be the skip-reads-as-
        # pass mistake again.
        reported = [line for line in outcome["lines"] if line.startswith("[FAIL]")]
        cells = f"{outcome['cells']} code cell" + ("s" if outcome["cells"] != 1 else "")
        tally = ""
        if outcome["lines"]:
            warned = sum(1 for line in outcome["lines"] if line.startswith("[warn]"))
            tally = (f"; {len(outcome['lines'])} checks, {len(reported)} failed"
                     + (f", {warned} warned" if warned else ""))
        if outcome["error"] or reported:
            detail = outcome["error"] or f"{len(reported)} check(s) reported FAIL"
            if "rook-ceph-rgw-nautiluss3.rook" in detail:
                # The in-cluster mirror does not resolve off NRP, and the notebooks only
                # fetch when nothing is staged -- so this error means the data step, not
                # the network, is what is missing.
                detail += (f"  -- data is not staged; run `nids-setup.py data "
                           f"--assignment {code}`")
            detail = printable(detail)
            results.append((code, "fail", detail))
            print(f"  [FAIL] {detail}")
        else:
            results.append((code, "ok", f"{cells}, no errors{tally}"))
            print(f"  [ ok ] {cells}, no errors{tally}")
        print()

    print("-" * 62)
    for code, state, detail in results:
        tag = {"ok": "[ ok ]", "fail": "[FAIL]", "warn": "[warn]", "skip": "[skip]"}[state]
        print(f"{tag} {code:11} {detail}")

    if args.dry_run:
        print("\n--dry-run: nothing was executed")
        return 0

    failed = [c for c, s, _ in results if s == "fail"]
    ready = [c for c, s, _ in results if s == "ok"]
    print()
    if failed:
        print(f"NOT ready to hand out: {', '.join(failed)}")
        return 1
    if not ready:
        # Every module warned. Saying "all green" here would be the skip-reads-as-pass
        # mistake the dataset checker already made once.
        print(f"nothing was verified -- no key repo under {root} had a notebook to run")
        return 0
    print(f"ready to hand out ({tier}): {', '.join(ready)}"
          + (f"; {len(results) - len(ready)} not verified, see above" if len(ready) != len(results) else ""))
    return 0


# --- clone -------------------------------------------------------------------------
# Registry mode only: the repo list is a known set of names read from
# assignments/registry.toml, so this makes no GitHub API call and needs no token. The
# organisation-listing mode -- which does need curl, jq and a token -- stays in
# scripts/clone-nids-repos.sh, because it is a maintainer tool rather than something a
# person setting up a module ever runs.


def github_token():
    """A token if one is available, else None. Only affects which protocol we clone over."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    if shutil.which("gh"):
        try:
            done = subprocess.run(["gh", "auth", "token"],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=15)
            if done.returncode == 0 and done.stdout.strip():
                return done.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def git(*args, **kwargs):
    """Run git, capturing output. GIT_TERMINAL_PROMPT=0 so a private repo fails rather
    than hanging on a password prompt -- which on Windows is a GUI dialog nobody sees."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, **kwargs)


NO_ACCESS = ("not found", "denied", "authentication", "could not read username")


def sync_one(name, url, ref, root, dry_run):
    """Clone or fast-forward one repo. Returns a one-line report, never raises.

    Idempotent: an existing checkout is fetched and fast-forwarded, never reset, and one
    with local changes or a diverged branch is reported and left exactly as it is. This
    has to be safe to re-run in a directory someone is working in.
    """
    dest = root / name
    if not dest.is_dir():
        if dry_run:
            return f"{name:<42} would clone"
        done = git("clone", "--quiet", url, str(dest))
        if done.returncode == 0:
            if ref:
                git("-C", str(dest), "checkout", "--quiet", ref)
            return f"{name:<42} cloned" + (f" at {ref}" if ref else "")
        err = (done.stderr or done.stdout).strip()
        if any(marker in err.lower() for marker in NO_ACCESS):
            return f"{name:<42} no access (private, or no token)"
        first = err.splitlines()[0] if err else "unknown error"
        return f"{name:<42} CLONE FAILED: {first}"
    if not (dest / ".git").is_dir():
        return f"{name:<42} skipped (not a git checkout)"
    if git("-C", str(dest), "status", "--porcelain").stdout.strip():
        return f"{name:<42} skipped (uncommitted changes)"
    if dry_run:
        return f"{name:<42} would fetch"
    git("-C", str(dest), "fetch", "--quiet", "--all", "--prune")
    if git("-C", str(dest), "merge", "--ff-only", "--quiet", "@{u}").returncode == 0:
        return f"{name:<42} updated"
    return f"{name:<42} left alone (diverged or no upstream)"


def cmd_clone(args):
    """Clone or update the module repos named by the registry."""
    if not shutil.which("git"):
        raise SystemExit("git is not installed, or not on PATH -- install it and re-run.\n"
                         "Windows: https://git-scm.com/download/win (choose 'Git from the "
                         "command line').")
    assignments, codes = select(args)
    root = find_root(getattr(args, "root", None))
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()

    token = github_token()
    # https is anonymous, so it is the right default only when we have no credentials.
    proto = args.proto or ("https" if not token else "ssh")

    wanted = []
    for code, assignment in assignments.items():
        if codes and code not in codes:
            continue
        roles = [assignment.repo]
        if args.include_key:
            roles.append(assignment.key_repo)
        for name in roles:
            if name:
                url = (f"git@github.com:{args.org}/{name}.git" if proto == "ssh"
                       else f"https://github.com/{args.org}/{name}.git")
                wanted.append((name, url, assignment.ref or ""))
    if not wanted:
        raise SystemExit("no modules matched")
    if args.include_key and not token:
        raise SystemExit("--include-key needs a GitHub token; every *-key repo is private")

    tier = args.release or "all"
    scope = f"{tier}, modules {','.join(sorted(codes))}" if codes else tier
    print(f"source: assignments/registry.toml ({scope})")
    print(f"root:   {root}")
    print(f"proto:  {proto}")
    if not token:
        print("auth:   none -- private modules will be reported and skipped")
    if args.dry_run:
        print("mode:   dry run")
    print()

    # Threads, not processes: every worker is waiting on git, and the results are
    # collected in registry order rather than finish order so the report is stable.
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        reports = list(pool.map(
            lambda item: sync_one(*item, root, args.dry_run), wanted))
    for line in reports:
        print(line)

    failed = sum(1 for line in reports if "CLONE FAILED" in line)
    noaccess = sum(1 for line in reports if "no access" in line)
    print(f"\n{len(wanted)} repositories in {root}")
    # `no access` is the expected outcome for someone without CAIDA membership, so it is
    # not a failure. A clone that broke for any other reason is.
    if noaccess:
        print(f"{noaccess} repository/ies you cannot read were skipped")
    if failed:
        sys.stderr.write(f"{failed} clone(s) FAILED -- nothing downstream will work "
                         "until they succeed\n")
        return 1
    return 0


# --- setup -------------------------------------------------------------------------
# The one command: clone, then environment, then data. Each step is also a subcommand
# you can run on its own, and this only sequences them -- so there is one implementation
# of each step, shared by every platform. setup.sh and setup.cmd are launchers that call
# straight through to here and hold no logic of their own.


class Selection:
    """The module selection, in the form each subcommand's parser expects."""

    def __init__(self, release, modules):
        self.release = release
        self.assignment = modules or None


def cmd_setup(args):
    """Clone the module repos, build one environment, and stage their data."""
    modules = ([m.strip().upper() for m in args.modules.split(",") if m.strip()]
               if args.modules else None)
    root = find_root(getattr(args, "root", None))
    sel = Selection(args.release, modules)

    skip_env, env_note = args.skip_env, "skipped (--skip-env)"
    if args.mode == "nrp" and not skip_env:
        # The hub image already carries every package; building a venv there would
        # shadow it and confuse the kernel the notebook actually runs in.
        skip_env, env_note = True, "skipped on NRP -- the hub image already provides the packages"

    where = f"{args.mode}, release {args.release}"
    if modules:
        where += f", modules {','.join(modules)}"
    print("=" * 62)
    print(f" NIDS setup -- {where}")
    print(f" repos go in: {root}")
    print("=" * 62)

    print("\n--- 1/3  cloning module repositories -------------------------")
    clone_args = argparse.Namespace(
        root=getattr(args, "root", None), release=args.release, assignment=sel.assignment,
        include_key=False, proto=None, org="CAIDA", jobs=args.jobs, dry_run=False)
    if cmd_clone(clone_args) != 0:
        sys.stderr.write(
            "\nStopping: the module repositories did not clone, so there is nothing to "
            "build\nan environment for or to download data into. Fix the errors above and "
            "re-run;\nthis script picks up where it left off.\n")
        return 1

    print("\n--- 2/3  building the Python environment ---------------------")
    venv = nids_registry.repo_root() / ".venv"
    if skip_env:
        print(env_note)
    else:
        env_args = argparse.Namespace(
            root=getattr(args, "root", None), release=args.release, assignment=sel.assignment,
            path=None, python=args.python, requirements_only=False,
            register_kernel=False, dry_run=False)
        status = cmd_env(env_args)
        if status:
            return status

    print("\n--- 3/3  staging data ----------------------------------------")
    if args.skip_data:
        print("skipped (--skip-data)")
    else:
        data_args = argparse.Namespace(
            root=getattr(args, "root", None), release=args.release, assignment=sel.assignment,
            nrp=(args.mode == "nrp"), force=False)
        status = cmd_data(data_args)
        if status:
            return status

    print()
    print("=" * 62)
    print(" Done. Next:")
    if not skip_env:
        print(f"   {activate_hint(venv)}")
        print(f"   jupyter lab {root}")
    else:
        print("   open a module's notebook in JupyterHub")
    print("=" * 62)
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
        ("setup", cmd_setup, "clone, build an environment, and stage data -- the one command"),
        ("clone", cmd_clone, "clone or update the module repos named by the registry"),
        ("discover", cmd_discover, "report what is cloned and what state it is in"),
        ("doctor", cmd_doctor, "discover, plus a dataset reachability pass"),
        ("env", cmd_env, "build one environment that runs the selected modules"),
        ("data", cmd_data, "stage each module's datasets into its own data/ directory"),
        ("verify", cmd_verify, "run each key repo's notebook and report what is ready to hand out"),
    ):
        p = sub.add_parser(name, help=help_text)
        # Also accepted after the subcommand, so `setup.sh --root DIR` works -- the
        # launchers pass every argument through after the subcommand name. SUPPRESS so an
        # unused subcommand default cannot overwrite a value given before it.
        p.add_argument("--root", default=argparse.SUPPRESS,
                       help="directory holding the cloned repos")
        p.add_argument("--assignment", action="append", metavar="CODE",
                       help="limit to one assignment code; repeatable")
        p.add_argument("--release", metavar="TIER",
                       help="limit to a release tier, e.g. r1"
                            + (" (default: r1)" if name == "setup" else " (default: every module)"))
        p.set_defaults(handler=handler)
        if name == "setup":
            # --release carries a default here and nowhere else: `setup` is the command a
            # newcomer runs, and it should mean "set up the shipping release".
            p.set_defaults(release="r1")
            where = p.add_mutually_exclusive_group(required=True)
            where.add_argument("--local", dest="mode", action="store_const", const="local",
                               help="set up on your own machine, using public data")
            where.add_argument("--nrp", dest="mode", action="store_const", const="nrp",
                               help="set up on NRP's JupyterHub, using the in-cluster mirror")
            p.add_argument("--modules", metavar="A,B",
                           help="only these modules (default: everything in the release)")
            p.add_argument("--python", metavar="EXE",
                           help="interpreter to build the environment with "
                                "(not the one running this)")
            p.add_argument("--jobs", type=int, default=4, metavar="N",
                           help="parallel clones (default: 4)")
            p.add_argument("--skip-env", action="store_true",
                           help="do not build a Python environment")
            p.add_argument("--skip-data", action="store_true",
                           help="do not download data")
        if name == "clone":
            p.add_argument("--include-key", action="store_true",
                           help="also clone the answer-key repos (needs a GitHub token)")
            p.add_argument("--proto", choices=("ssh", "https"),
                           help="clone protocol (default: https anonymously, ssh with a token)")
            p.add_argument("--org", default="CAIDA", help="GitHub organisation")
            p.add_argument("--jobs", type=int, default=4, metavar="N",
                           help="parallel clones (default: 4)")
            p.add_argument("--dry-run", action="store_true",
                           help="print what would happen, change nothing")
        if name == "verify":
            p.add_argument("--path", metavar="DIR",
                           help="the environment to run in (default: <nids-setup>/.venv)")
            p.add_argument("--python", metavar="EXE",
                           help="interpreter to run the notebooks with, instead of --path's")
            p.add_argument("--timeout", type=int, default=900, metavar="SECONDS",
                           help="per-notebook time limit (default: 900)")
            p.add_argument("--dry-run", action="store_true",
                           help="print which notebook each module would run, run nothing")
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
