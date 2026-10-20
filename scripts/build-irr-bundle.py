#!/usr/bin/env python3
"""Build the fixed-input bundle for the IRR module (nids-irr-rpki-whois).

  scripts/build-irr-bundle.py --out ~/irr-bundle --accept-gaps
  scripts/build-irr-bundle.py --out ~/irr-bundle --dates 2023-03-01 --kinds rpki

The IRR notebooks parse three sources -- IRR dumps, RIPE RPKI ROAs and RouteViews
prefix2as -- and cache one table per source per day under `cache_nids/`
(`irr_<day>.csv.gz`, `rpki_<day>.csv.gz`, `prefix2as_<day>.csv.gz`). Every loader reads
that cache before fetching anything, so a notebook whose `cache_nids/` is pre-populated
never touches the network. This script produces exactly those files, plus a manifest,
packed so that unpacking the tarball in the module directory populates `cache_nids/`.

The parsing is not reimplemented here. The loader cells are executed from the notebook
itself (the key, by default), so the bundle is what the notebook would have cached, and
the dates are the notebook's own `SAMPLE_DATE` and `MONTHLY_SNAPSHOT_DATES` unless
`--dates` overrides them. The answer cache (`irr_rpki_consistency_*`) is never produced.

Run it where the notebook's sources resolve: the IRR dumps and prefix2as are read from
the in-cluster Ceph endpoint, so that means the NRP hub.

Gaps are reported, never hidden. The notebook skips an unreadable IRR file with a print
and caches whatever it got; here a day missing any IRR source or RPKI trust anchor, or
with no prefix2as rows, fails the build unless `--accept-gaps` is given, and every gap is
recorded in MANIFEST.json either way.
"""

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile

DEFAULT_NOTEBOOK = "../nids-irr-rpki-whois-key/nids-irr-rpki-whois-key.ipynb"
KINDS = ("irr", "rpki", "prefix2as")

# The loader cells run from the one that defines CACHE_DIR through the one that defines
# load_prefix2as_snapshot. Found by content, not by index, so added cells do not shift it.
FIRST_MARKER = 'CACHE_DIR = Path("cache_nids")'
LAST_MARKER = "def load_prefix2as_snapshot("


def loader_source(notebook):
    cells = [
        "".join(c["source"])
        for c in json.loads(notebook.read_text())["cells"]
        if c["cell_type"] == "code"
    ]
    first = next((i for i, s in enumerate(cells) if FIRST_MARKER in s), None)
    last = next((i for i, s in enumerate(cells) if LAST_MARKER in s), None)
    if first is None or last is None or last < first:
        raise SystemExit(f"{notebook}: cannot find the loader cells "
                         f"({FIRST_MARKER!r} .. {LAST_MARKER!r})")
    # Drop IPython magics and shell escapes; nothing in the loader cells needs them.
    return "\n\n".join(
        "\n".join(l for l in s.splitlines() if not l.lstrip().startswith(("%", "!")))
        for s in cells[first:last + 1]
    )


def git_state(path):
    def git(*args):
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                              text=True).stdout.strip()
    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--", "."))
    return {"commit": commit or None, "dirty": dirty}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True,
                    help="empty or new directory to build in; the tarball is written here")
    ap.add_argument("--notebook", default=None,
                    help=f"notebook to take the loaders from (default: {DEFAULT_NOTEBOOK}, "
                         "relative to this repo)")
    ap.add_argument("--dates", nargs="+",
                    help="YYYY-MM-DD days to build (default: the notebook's SAMPLE_DATE "
                         "and MONTHLY_SNAPSHOT_DATES)")
    ap.add_argument("--kinds", nargs="+", choices=KINDS, default=list(KINDS),
                    help="which tables to build (default: all three)")
    ap.add_argument("--accept-gaps", action="store_true",
                    help="build even when a day is missing sources; the gaps still go in "
                         "MANIFEST.json")
    args = ap.parse_args()

    repo = pathlib.Path(__file__).resolve().parent.parent
    notebook = (pathlib.Path(args.notebook).expanduser().resolve() if args.notebook
                else (repo / DEFAULT_NOTEBOOK).resolve())
    if not notebook.is_file():
        raise SystemExit(f"no notebook at {notebook}")

    out = pathlib.Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        # A leftover cache from an earlier run would be bundled as if freshly built.
        raise SystemExit(f"{out} is not empty -- give a new directory")

    source = loader_source(notebook)
    os.chdir(out)  # the notebook's CACHE_DIR is relative: cache_nids/ lands here
    ns = {"__name__": "irr_bundle"}
    exec(compile(source, f"{notebook.name}:loader-cells", "exec"), ns)
    # tqdm.notebook needs a Jupyter front end; the plain bar behaves the same here.
    from tqdm import tqdm
    ns["tqdm"] = tqdm

    if args.dates:
        days = sorted(set(args.dates))
    else:
        days = sorted({ns["day_str"](d) for d in
                       [ns["SAMPLE_DATE"], *ns["MONTHLY_SNAPSHOT_DATES"]]})
    print(f"notebook: {notebook}")
    print(f"days:     {', '.join(days)}")
    print(f"kinds:    {', '.join(args.kinds)}\n")

    loaders = {"irr": ns["load_irr_snapshot"], "rpki": ns["load_rpki_snapshot"],
               "prefix2as": ns["load_prefix2as_snapshot"]}
    gaps = {}
    for day in days:
        for kind in args.kinds:
            df = loaders[kind](day, force_refresh=True)
            missing = []
            if kind == "irr":
                have = set(df["source"]) if "source" in df else set()
                missing = sorted(set(ns["IRR_SOURCES"]) - have)
            elif kind == "rpki":
                have = set(df["trust_anchor"]) if "trust_anchor" in df else set()
                missing = sorted(set(ns["RPKI_TRUST_ANCHORS_2023"]) - have)
            elif df.empty:
                missing = ["no rows"]
            print(f"{day} {kind:<9} {len(df):>9,} rows"
                  + (f"   MISSING: {', '.join(missing)}" if missing else ""))
            if missing:
                gaps.setdefault(day, {})[kind] = missing

    cache = out / "cache_nids"
    files = {}
    for day in days:
        for kind in args.kinds:
            path = cache / f"{kind}_{day}.csv.gz"
            files[f"cache_nids/{path.name}"] = {"md5": md5(path),
                                                "bytes": path.stat().st_size}
    (cache / "MD5SUMS").write_text(
        "".join(f"{v['md5']}  {k.split('/', 1)[1]}\n" for k, v in sorted(files.items())))
    manifest = {
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "notebook": notebook.name,
        "notebook_repo": git_state(notebook.parent),
        "builder_repo": git_state(repo),
        "days": days,
        "kinds": args.kinds,
        "gaps": gaps,
        "files": files,
    }
    (cache / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")

    if gaps and not args.accept_gaps:
        raise SystemExit(f"\n{sum(len(v) for v in gaps.values())} gap(s) above; nothing "
                         "packed. Re-run with --accept-gaps to bundle them as they are.")

    tarball = out / f"irr-rpki-bundle_{days[0]}_{days[-1]}.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        for name in ["cache_nids/MANIFEST.json", "cache_nids/MD5SUMS", *sorted(files)]:
            tar.add(out / name, arcname=name)
    print(f"\n{tarball}  ({tarball.stat().st_size / 1e6:.1f} MB, md5 {md5(tarball)})")
    if gaps:
        print("built WITH gaps -- see MANIFEST.json")


if __name__ == "__main__":
    sys.exit(main())
