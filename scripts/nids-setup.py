#!/usr/bin/env python3
"""Set up the NIDS assignments from one directory of cloned repositories.

  scripts/nids-setup.py discover              what is here, and what state it is in
  scripts/nids-setup.py doctor                discover, plus a reachability pass
  scripts/nids-setup.py doctor --assignment BGP
  scripts/nids-setup.py env --venue local     one environment that runs ASN and BGP
  scripts/nids-setup.py data --release r1     stage each module's data into its data/ dir
  scripts/nids-setup.py verify --release r1   run the key notebooks; what is ready to hand out

The repos come from scripts/clone-nids-repos.sh; the metadata comes from the two
registries (datasets/<id>/dataset.toml and assignments/registry.toml, documented in
datasets/SCHEMA.md).

`discover` and `doctor` are read-only. `env` writes a generated requirements file and, unless
--dry-run, a virtual environment. `data` writes into each module's data/ directory. `verify`
executes notebooks but saves nothing -- it needs the -key repos, which are private, so it is an
instructor-side command.

Module selection is the same on every subcommand, and there are two axes because they answer
different questions. --venue is physical: where a module can be run (local, nrp, expanse), and
--venue local is ASN and BGP. --release is editorial: which round a module ships in.
--assignment picks individual codes. All three combine as an intersection, and with none of
them every registered module is in scope.

Root directory, in order: --root, $NIDS_ROOT, the parent of this checkout.
"""

import argparse
import concurrent.futures
import gzip
import json
import os
import pathlib
import re
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


def codes_from(values):
    """Normalise --assignment into upper-case codes, or None.

    Accepts both the repeatable form (--assignment ASN --assignment BGP) and the comma
    form (--assignment ASN,BGP), because people reach for both and neither is wrong.
    """
    if not values:
        return None
    codes = [c.strip().upper() for v in values for c in str(v).split(",") if c.strip()]
    return codes or None


def select(args):
    """(assignments, codes) for this invocation -- the one place selection is decided."""
    release = getattr(args, "release", None)
    venue = getattr(args, "venue", None)
    assignments = nids_registry.load_assignments(release=release, venue=venue)
    if not assignments:
        scope = ", ".join(f"{k} = {v!r}" for k, v in
                          (("release", release), ("venue", venue)) if v)
        if scope:
            raise SystemExit(f"no modules with {scope} in assignments/registry.toml")
        raise SystemExit("assignments/registry.toml is missing -- nothing to do")
    codes = None
    if codes_from(getattr(args, "assignment", None)):
        codes = set(codes_from(args.assignment))
        unknown = codes - set(assignments)
        if unknown:
            known = ", ".join(sorted(assignments))
            # Name the filter that excluded them: "unknown code DNS" is baffling when the
            # real answer is that DNS exists but is not a local module.
            scope = ""
            if venue:
                scope = f" for venue {venue}"
            elif release:
                scope = f" in release {release}"
            raise SystemExit(f"unknown assignment code{scope}: {', '.join(sorted(unknown))}"
                             f"\nknown{scope}: {known}")
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
        # For IYP this is a real gap rather than a nicety, since it targets JupyterHub.
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


# Java is not a Python package, and `pyspark` is only a wrapper around a JVM: pip installs
# it happily on a machine with no `java`, and the failure then surfaces as a Spark stack
# trace at notebook run time, long after setup looked like it worked. Checking here turns
# that into one line while the user is still in the terminal that could fix it.
JVM_PACKAGE = "pyspark"


def requirement_name(line):
    """The bare package name from a requirements line, without marker or specifier."""
    return re.split(r"[;\[<>=!~ ]", line.strip(), maxsplit=1)[0].lower()


def java_runtime():
    """The `java` this machine would run, or None. JAVA_HOME wins over PATH, as on a JVM."""
    home = os.environ.get("JAVA_HOME")
    if home:
        candidate = (pathlib.Path(home) / "bin"
                     / ("java.exe" if os.name == "nt" else "java"))
        if candidate.is_file():
            return str(candidate)
    return shutil.which("java")


def jvm_modules(assignments, codes):
    """Selected modules whose dependencies need a JVM, in registry order."""
    return [code for code, a in assignments.items()
            if (not codes or code in codes)
            and any(requirement_name(pkg) == JVM_PACKAGE
                    for pkg in a.env_for("assignment").get("extra", []))]


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
    # A venue selection and a release selection are different sets and must not share a
    # generated file: a venue selection and a release selection can diverge at any time.
    tier = getattr(args, "venue", None) or args.release or "all"
    # The filename tracks the whole selection: a subset must not overwrite the tier's file.
    slug = tier if not codes else "-".join(selected).lower()
    label = f"{tier} / {','.join(selected)}" if codes else tier

    text = requirements_text(assignments, codes, label)
    packages = packages_in(text)
    req_path = nids_registry.repo_root() / "env" / f"requirements-{slug}.txt"

    print(f"selection:    {label}")
    print(f"modules:      {', '.join(selected)}")
    print(f"requirements: {req_path.name} ({len(packages)} packages)")

    # Reported for the whole selection, before anything is built: it is a property of what
    # was asked for, and the other modules in the same selection still work without it.
    needs_jvm = jvm_modules(assignments, codes)
    if needs_jvm and not java_runtime():
        others = [c for c in selected if c not in needs_jvm]
        print(f"  [warn] {', '.join(needs_jvm)} needs a Java runtime and this machine has "
              "none --")
        print(f"         no `java` on PATH, no JAVA_HOME. `{JVM_PACKAGE}` is a wrapper "
              "around a JVM,")
        print("         so pip installs it but the notebook fails at run time. Install a "
              "JDK (17 or")
        print("         newer), or run that module on NRP's JupyterHub, which has one.")
        if others:
            print(f"         Unaffected, and still built by this run: {', '.join(others)}.")

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

    # A dataset may override the mode's source. as2org needs it: the in-cluster object is
    # undated and refreshed in place, so reading it on NRP while a local run reads a pinned
    # serial gives two different answers to the same graded question -- and the notebooks
    # cannot tell, because the URL carries no version. `source = "public"` in [stage] means
    # "always the pinned public release", which is what makes a key and a student agree.
    if dataset.stage.get("source") == "public":
        source = "local"
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

    **Both the student repo and the `-key` repo are staged**, whichever of them is cloned.
    Staging only the student repo was a real defect: the key notebooks read the same
    relative `data/` paths, so whatever a person last left there is what a key is graded
    against. On 2026-09-09 that was a `20260801` as2org file from the 2026-09-03 rehearsal,
    while the student repo held the pinned `20260501` -- exactly the key/student vintage
    split that `[stage] source = "public"` and `serial = "20260501"` exist to prevent.
    A repo that is not cloned is skipped, as before.
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
        wanted = [(datasets[e["id"]], assignment.pins_for(e["id"]))
                  for e in assignment.datasets
                  if e["id"] in datasets and datasets[e["id"]].stage]
        if not wanted:
            continue
        print(f"{code}")

        # Student repo and key repo both read `data/<file>` relative to themselves, so both
        # need staging; see this function's docstring for what staging only the first cost.
        targets = [name for name in (assignment.repo, assignment.key_repo) if name]
        cloned = [(name, root / name) for name in targets if (root / name).is_dir()]
        if not cloned:
            print(f"  skipped -- {' / '.join(targets)} not cloned under {root}")
            continue

        for name, repo in cloned:
            if len(cloned) > 1:
                print(f"  {name}")
            prefix = "    " if len(cloned) > 1 else "  "
            for dataset, pins in wanted:
                if code not in dataset.stage.get("into", [code]):
                    continue
                line = stage_one(dataset, pins, repo / "data", source, args.force)
                print(f"{prefix}{line}")
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
    tier = getattr(args, "venue", None) or args.release or "all"

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

    tier = getattr(args, "venue", None) or args.release or "all"
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

    def __init__(self, release, modules, venue=None):
        self.release = release
        self.venue = venue
        self.assignment = modules or None


def cmd_setup(args):
    """Clone the module repos, build one environment, and stage their data."""
    modules = codes_from(getattr(args, "assignment", None))
    root = find_root(getattr(args, "root", None))

    # What a mode selects when the user names nothing. --local means "the modules that run
    # here", which is a venue question, not a release one: selecting release 1 on a laptop
    # would pull in DNS and try to install pyspark against a JVM that is not there. --nrp
    # means "the modules shipping in this release", because the hub runs all of them.
    release, venue = args.release, None
    if args.mode == "local" and not modules:
        release, venue = None, "local"
    sel = Selection(release, modules, venue)

    skip_env, env_note = args.skip_env, "skipped (--skip-env)"
    if args.mode == "nrp" and not skip_env:
        # The hub image already carries every package; building a venv there would
        # shadow it and confuse the kernel the notebook actually runs in.
        skip_env, env_note = True, "skipped on NRP -- the hub image already provides the packages"

    if args.mode == "local" and modules:
        # Only reachable when the user named modules explicitly. Warn rather than refuse:
        # a hub module may well run on a laptop that happens to have the right host
        # prerequisite, and we would rather someone try it than be stopped by a claim.
        offhub = [code for code, a in nids_registry.load_assignments().items()
                  if not a.runs_local and code in modules]
        if offhub:
            print(f"note: {', '.join(offhub)} {'is' if len(offhub) == 1 else 'are'} supported "
                  f"on the NRP hub, not on a laptop.\n"
                  f"      Setup will still run and may well work, but it is untested and "
                  f"unsupported;\n"
                  f"      see the module's README for what its venue needs.\n")

    where = args.mode if venue else f"{args.mode}, release {release}"
    if modules:
        where += f", modules {','.join(modules)}"
    print("=" * 62)
    print(f" NIDS setup -- {where}")
    print(f" repos go in: {root}")
    print("=" * 62)

    print("\n--- 1/3  cloning module repositories -------------------------")
    clone_args = argparse.Namespace(
        root=getattr(args, "root", None), release=sel.release, venue=sel.venue,
        assignment=sel.assignment,
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
            root=getattr(args, "root", None), release=sel.release, venue=sel.venue,
            assignment=sel.assignment,
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
            root=getattr(args, "root", None), release=sel.release, venue=sel.venue,
            assignment=sel.assignment,
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


# --- prep --------------------------------------------------------------------------
# Phase 5, the instructor path. `verify` answers "does this run?"; `prep` answers the
# question an instructor actually asks -- "can I hand this out on Monday, and what do I
# have to do first?" It is deliberately a report rather than an action: nothing here
# writes to a repo, because an instructor's first run of an unfamiliar tool should not
# change anything.
#
# Explicitly out of scope: generating student repos from key repos, which is
# nids-module-creator's job, and anything touching GitHub Classroom.

# Paths that are noise in a key-vs-student comparison: build droppings, the staged data
# the tooling puts there, and the checkpoints Jupyter writes beside every notebook.
_INVENTORY_SKIP = (".git", ".ipynb_checkpoints", "__pycache__", "data", ".venv")


def repo_inventory(path):
    """Relative paths of the content files in a module checkout.

    `git ls-files` when the checkout is a repo, so a gitignored artifact never reads as a
    difference between the two repos; a filesystem walk otherwise, because a downloaded
    zip is a perfectly reasonable way to have a module.
    """
    if (path / ".git").exists() and shutil.which("git"):
        done = subprocess.run(["git", "-C", str(path), "ls-files"],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if done.returncode == 0:
            return {line for line in done.stdout.splitlines() if line
                    and not line.startswith(_INVENTORY_SKIP)}
    found = set()
    for entry in path.rglob("*"):
        if entry.is_dir():
            continue
        rel = entry.relative_to(path)
        if any(part in _INVENTORY_SKIP for part in rel.parts):
            continue
        found.add(rel.as_posix())
    return found


def _notebook_stem(name):
    """`nids-asn-introduction-key.ipynb` -> `nids-asn-introduction`, so the two repos'
    notebooks can be matched across the naming convention rather than by filename."""
    stem = pathlib.PurePosixPath(name).stem
    return stem[:-4] if stem.endswith("-key") else stem


def prep_inventory(code, assignment, root):
    """(b) Does every notebook the students get have an answer in the key?

    The spec asked for a file-level diff of the two repos, and the first implementation
    did exactly that -- which turned out to be useless here. A key repo holds a README and
    one notebook; the student repo holds all the prose, images and slides. So *every*
    student file is "missing from the key", every time, and a report that fires on all of
    them teaches the reader to skip this section.

    What is actually diagnostic is narrower: a notebook handed to students with no
    counterpart in the key means an instructor is about to assign work they have no answer
    for. That is the failure. The rest of the file difference is printed as a count, for
    orientation only.
    """
    lines, problems = [], 0
    key_path = root / assignment.key_repo if assignment.key_repo else None
    student_path = root / assignment.repo if assignment.repo else None
    if not (key_path and key_path.is_dir()):
        return [f"[warn] {assignment.key_repo or 'no key repo'} is not cloned -- "
                f"nothing to compare"], 0
    if not (student_path and student_path.is_dir()):
        return [f"[warn] {assignment.repo or 'no student repo'} is not cloned -- "
                f"clone it to compare against the key"], 0

    key_files, student_files = repo_inventory(key_path), repo_inventory(student_path)
    key_stems = {_notebook_stem(f) for f in key_files if f.endswith(".ipynb")}
    unanswered = sorted(f for f in student_files
                        if f.endswith(".ipynb") and _notebook_stem(f) not in key_stems)
    if unanswered:
        problems += 1
        lines.append(f"[FAIL] {len(unanswered)} student notebook(s) with no answer key:")
        lines.extend(f"         {name}" for name in unanswered)
    else:
        answered = sum(1 for f in student_files if f.endswith(".ipynb"))
        lines.append(f"[ ok ] every student notebook has a key ({answered} notebook"
                     + ("s" if answered != 1 else "") + ")")

    # Orientation only. A key repo is a companion, not a copy, so these counts are
    # expected to be lopsided -- they are here to make an *empty* student repo or a key
    # that has quietly accumulated material visible, not to be zero.
    only_key = sorted(key_files - student_files)
    only_student = sorted(student_files - key_files)
    lines.append(f"[ ok ] {len(only_student)} file(s) only in the student repo, "
                 f"{len(only_key)} only in the key")
    extras = [f for f in only_key if not f.endswith(".ipynb") and f not in {".gitignore", "README.md"}]
    if extras:
        lines.append("       instructor-only material: " + ", ".join(extras[:6])
                     + (" ..." if len(extras) > 6 else ""))
    return lines, problems


def checker_python(args=None):
    """The interpreter to run check-datasets.py in: the built environment when there is one.

    `sys.executable` is whatever launched this CLI, which on a laptop is the system Python
    and does not have `pelicanfs` -- so the OSDF probe reported "skipped: pip install
    pelicanfs" while the package sat installed in .venv two directories away. A skipped
    check is not a passing check, and this one was skipping for a reason that had nothing
    to do with the dataset.
    """
    if args is not None and getattr(args, "python", None):
        found = shutil.which(args.python) or args.python
        return str(pathlib.Path(found).resolve())
    venv = pathlib.Path(args.path).expanduser().resolve() \
        if args is not None and getattr(args, "path", None) \
        else nids_registry.repo_root() / ".venv"
    return str(venv_python(venv) or sys.executable)


def prep_datasets(code, args=None):
    """(c) Are this module's pinned coordinates still reachable?

    A subprocess for the same reason `doctor` uses one: check-datasets.py owns the
    exit-code contract, and a second implementation of it here is exactly the drift this
    tooling exists to remove. Pin freshness is not hypothetical -- BGP pins a RouteViews
    month and ASN a customer-cone serial, and a release that ships a stale pin fails on
    the instructor's first run rather than ours.
    """
    checker = nids_registry.repo_root() / "scripts" / "check-datasets.py"
    done = subprocess.run([checker_python(args), str(checker), "--assignment", code],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return lines, (1 if done.returncode else 0)


def prep_venue(assignment):
    """(d) Where this module is supported, and what the instructor needs to teach it.

    Venue comes first because it is the fact that decides everything else: an instructor
    reading this needs to know whether to send students to a laptop or to arrange
    namespace access before term starts, and the second answer has a lead time.
    """
    lines = []
    venue = ", ".join(assignment.venue)
    if assignment.runs_local:
        lines.append(f"[ ok ] venue: {venue} -- students can run this on their own machines")
    elif "expanse" in assignment.venue:
        lines.append(f"[ ok ] venue: {venue} -- runs under Slurm on SDSC Expanse, not on the "
                     f"hub; students need their own allocation")
    else:
        lines.append(f"[ ok ] venue: {venue} -- students need access to that venue; the "
                     f"laptop path is untested and unsupported")
    memory = assignment.memory or {}
    if memory:
        envelope = f"{memory.get('guarantee', '?')} guaranteed, {memory.get('limit', '?')} limit"
        measured = "" if memory.get("verified") else "  (from the registry; not measured)"
        lines.append(f"[ ok ] memory profile: {envelope}{measured}")
        if assignment.raw.get("profile"):
            lines.append("       needs its own spawner profile on the hub -- see "
                         "docs/4_nrp_jupyterhub.md")
    else:
        lines.append("[ ok ] memory profile: none in the registry -- the hub default applies")
    if assignment.status != "active":
        blocked = assignment.raw.get("blocked_on")
        lines.append(f"[warn] module status is {assignment.status!r}"
                     + (f" -- blocked on {blocked}" if blocked else ""))
    if assignment.release != "r1":
        lines.append(f"[warn] release is {assignment.release!r}, not r1 -- this module is "
                     f"not part of the shipping release")
    return lines


def cmd_prep(args):
    """Report what an instructor must do before handing a module out.

    Four checks per module, in the order an instructor needs them: where it runs, whether
    its data is still where the registry says, whether the key and student repos agree,
    and whether the key notebook actually runs. The last is by far the slowest, which is
    why --skip-verify exists and why it is the last thing printed.
    """
    root = find_root(getattr(args, "root", None))
    assignments, codes = select(args)
    selected = {code: a for code, a in assignments.items()
                if not codes or code in codes}
    if not selected:
        raise SystemExit("no modules matched")

    print(f"root:    {root}")
    print(f"modules: {', '.join(selected)}\n")

    summary = []
    for code, assignment in selected.items():
        print("=" * 62)
        print(f" {code} -- {assignment.name}")
        print("=" * 62)
        problems, unchecked = 0, 0

        def report(lines):
            """Print a check's lines and count the ones that mean "not actually checked".

            A [warn] here is never a pass. Two release-1 datasets read as fine for weeks
            because the packages that would have tested them were absent, and a `prep`
            that prints "ready to hand out" over an uncloned key repo would repeat that
            mistake in the one command an instructor trusts.
            """
            skipped = 0
            for line in lines:
                print(f"  {printable(line)}")
                if line.startswith("[warn]"):
                    skipped += 1
            return skipped

        print("\n1/4  where it runs")
        unchecked += report(prep_venue(assignment))

        print("\n2/4  pinned datasets")
        if args.skip_datasets:
            print("  [skip] --skip-datasets")
            unchecked += 1
        else:
            lines, bad = prep_datasets(code, args)
            problems += bad
            unchecked += report(lines)

        print("\n3/4  key repo against student repo")
        lines, bad = prep_inventory(code, assignment, root)
        problems += bad
        unchecked += report(lines)

        print("\n4/4  the key notebook")
        if args.skip_verify:
            print("  [skip] --skip-verify")
            unchecked += 1
        else:
            verify_args = argparse.Namespace(
                root=getattr(args, "root", None), release=args.release,
                assignment=[code], path=args.path, python=args.python,
                timeout=args.timeout, dry_run=args.dry_run)
            # cmd_verify prints its own report; its return code is the ready/not-ready
            # answer for this one module.
            problems += 1 if cmd_verify(verify_args) else 0

        summary.append((code, problems, unchecked))
        print()

    print("-" * 62)
    for code, problems, unchecked in summary:
        if problems:
            tag, detail = "[FAIL]", f"{problems} check(s) need attention -- see above"
        elif unchecked:
            tag = "[warn]"
            detail = (f"nothing failed, but {unchecked} check(s) did not run -- "
                      f"not confirmed ready")
        else:
            tag, detail = "[ ok ]", "ready to hand out"
        print(f"{tag} {code:11} {detail}")

    blocked = [c for c, problems, _ in summary if problems]
    partial = [c for c, problems, unchecked in summary if not problems and unchecked]
    ready = [c for c, problems, unchecked in summary if not problems and not unchecked]
    print()
    if blocked:
        print(f"NOT ready: {', '.join(blocked)}")
    if partial:
        print(f"not confirmed (checks skipped or unavailable): {', '.join(partial)}")
    if ready:
        print(f"ready to hand out: {', '.join(ready)}")
    elif not blocked:
        print("nothing was confirmed ready -- every module had a check that did not run")
    return 1 if blocked else 0


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
        cmd = [checker_python(args), str(checker)] + (["--assignment", code] if code else [])
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
        ("prep", cmd_prep, "the instructor path -- what to do before handing a module out"),
    ):
        p = sub.add_parser(name, help=help_text)
        # Also accepted after the subcommand, so `setup.sh --root DIR` works -- the
        # launchers pass every argument through after the subcommand name. SUPPRESS so an
        # unused subcommand default cannot overwrite a value given before it.
        p.add_argument("--root", default=argparse.SUPPRESS,
                       help="directory holding the cloned repos")
        p.add_argument("--assignment", action="append", metavar="CODE",
                       help="limit to these assignment codes; repeatable, and accepts a "
                            "comma-separated list")
        p.add_argument("--release", metavar="TIER",
                       help="limit to a release tier, e.g. r1"
                            + (" (default: r1)" if name == "setup" else " (default: every module)"))
        if name != "setup":
            # `setup` derives the venue from --local/--nrp instead, so offering both there
            # would be two ways to say one thing.
            p.add_argument("--venue", choices=("local", "nrp", "expanse"),
                           help="limit to modules supported at this venue; "
                                "'local' is ASN and BGP")
        p.set_defaults(handler=handler)
        if name == "setup":
            # --release carries a default here and nowhere else: `setup` is the command a
            # newcomer runs, and it should mean "set up the shipping release". On --local
            # cmd_setup replaces it with the local venue, which is the narrower answer.
            p.set_defaults(release="r1")
            where = p.add_mutually_exclusive_group(required=True)
            where.add_argument("--local", dest="mode", action="store_const", const="local",
                               help="set up on your own machine, using public data")
            where.add_argument("--nrp", dest="mode", action="store_const", const="nrp",
                               help="set up on NRP's JupyterHub, using the in-cluster mirror")
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
        if name in ("verify", "prep"):
            p.add_argument("--path", metavar="DIR",
                           help="the environment to run in (default: <nids-setup>/.venv)")
            p.add_argument("--python", metavar="EXE",
                           help="interpreter to run the notebooks with, instead of --path's")
            p.add_argument("--timeout", type=int, default=900, metavar="SECONDS",
                           help="per-notebook time limit (default: 900)")
            p.add_argument("--dry-run", action="store_true",
                           help="print which notebook each module would run, run nothing")
        if name == "prep":
            p.add_argument("--skip-verify", action="store_true",
                           help="do not run the key notebook (much faster; the other "
                                "three checks still run)")
            p.add_argument("--skip-datasets", action="store_true",
                           help="do not probe the pinned dataset coordinates")
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
