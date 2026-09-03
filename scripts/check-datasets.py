#!/usr/bin/env python3
"""Check that every NIDS dataset is reachable from outside the NRP cluster.

Every coordinate comes from the registry -- datasets/<id>/dataset.toml -- so this
script holds no dataset paths of its own. Editing a path means editing the registry,
which is also what the setup tooling reads.

Full walkthrough: datasets/README.md

The in-cluster counterpart is notebooks/check-datasets.ipynb, which runs the same
checks from inside a spawned server and can additionally reach Ceph. This script
covers what a laptop can see: OSDF, ftp.ripe.net, OpenINTEL, manycast.net, the
public IYP bolt endpoint, and -- when credentials are present -- the Expanse
FlowTuple bucket and the ITDK Postgres database.

The six Ceph-hosted datasets cannot resolve from outside NRP. They are reported
as warnings with an explanation, not failures, and do not affect the exit code.

Usage:
  scripts/check-datasets.py
  scripts/check-datasets.py --list
  UCSD_NT_S3_ACCESS_KEY=... UCSD_NT_S3_SECRET_KEY=... scripts/check-datasets.py
  ITDK_READ_DSN=postgresql://... scripts/check-datasets.py

Environment:
  UCSD_NT_S3_ACCESS_KEY   optional. Enables the Expanse FlowTuple check; both this
  UCSD_NT_S3_SECRET_KEY   and the secret key must be set or the check is skipped.
  ITDK_READ_DSN           optional. Enables the ITDK Postgres check. Needs a
                          `kubectl port-forward svc/postgres-service 5432:5432`
                          running, since the service is ClusterIP only.

Exit status is 0 when every *required* check passed, 1 otherwise. Ceph, the two
credential-gated datasets, and any check skipped for a missing dependency are not
required and never fail the run.
"""

import argparse
import importlib
import os
import socket
import sys
import urllib.error
import urllib.request

import nids_registry


def have(module_name):
    """True if an optional dependency is importable.

    A dataset whose client library is missing is not a broken dataset, so the
    matching check is downgraded to a warning rather than failing the run.
    """
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


# --- check runner -------------------------------------------------------------
# Self-contained on purpose: this runner is duplicated verbatim from
# notebooks/test.ipynb rather than imported. Every environment check in the NIDS
# repos carries its own byte-identical copy, because each is handed around as a
# single file into a fresh server. Keep it identical when editing.

RESULTS = []  # (label, "ok" | "fail" | "warn")


class check:
    """`with check("label") as c:` -- runs the body, records the outcome, never raises.

    Set `c.note = "..."` inside the body to add detail to the printed line.
    `required=False` downgrades a failure to a warning, which does not block "ready".
    """

    def __init__(self, label, required=True):
        self.label = label
        self.required = required
        self.note = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            RESULTS.append((self.label, "ok"))
            print(f"[ ok ] {self.label}" + (f"  ({self.note})" if self.note else ""))
        else:
            RESULTS.append((self.label, "fail" if self.required else "warn"))
            tag = "FAIL" if self.required else "warn"
            print(f"[{tag}] {self.label}  ->  {exc.__class__.__name__}: {exc}")
        return True  # swallow the exception so the remaining checks still run


def http_head(url, timeout=60):
    """HEAD a URL. Raises on a non-2xx status or a connection failure."""
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.headers


def http_first_bytes(url, n=64, timeout=60):
    """Range-GET the first n bytes of a URL -- never pulls the whole object."""
    req = urllib.request.Request(url, headers={"Range": f"bytes=0-{n - 1}"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(n)


def human_size(headers):
    size = headers.get("Content-Length")
    return f"{int(size) / 2**20:.0f} MiB" if size else "size unknown"


def report():
    """Print the verdict and return the process exit status. Call this last.

    Diverges from test.ipynb's report() only in the verdict wording: that one
    answers "is the hub ready", this one answers "are the datasets reachable",
    and it returns an exit code for scripting.
    """
    failed = [label for label, state in RESULTS if state == "fail"]
    warned = [label for label, state in RESULTS if state == "warn"]
    print()
    for label in warned:
        print(f"warning: {label} did not pass -- not required, see the note above")
    if failed:
        print(f"NOT reachable - {len(failed)} of {len(RESULTS)} checks failed:")
        for label in failed:
            print(f"  - {label}")
        print("\nWhat each dataset needs: nids-setup/datasets/README.md")
        return 1
    print(f"all required datasets reachable ({len(RESULTS)} checks, {len(warned)} skipped)")
    return 0


# --- in-cluster Ceph (NRP-internal hostname) -----------------------------------
CEPH = "http://rook-ceph-rgw-nautiluss3.rook"


def _ceph(call, path, *args, **kwargs):
    try:
        return call(f"{CEPH}/{path}", *args, **kwargs)
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), socket.gaierror):
            raise RuntimeError(
                f"{CEPH} did not resolve. That hostname only exists inside the NRP "
                "cluster -- this will never work from a laptop."
            ) from None
        raise


def ceph_head(path, **kwargs):
    return _ceph(http_head, path, **kwargs)


def ceph_first_bytes(path, n=64, **kwargs):
    return _ceph(http_first_bytes, path, n, **kwargs)


# --- registry-driven checks --------------------------------------------------
# There are no dataset paths in this file. Each check below is dispatched on the
# `kind` in datasets/<id>/dataset.toml [check], and every URL it touches is
# resolved from that dataset's template and defaults. When a coordinate goes
# stale, datasets/<id>/dataset.toml is the one place that needs editing -- the
# values table in the matching README.md is prose about the same fact.


def run_check(dataset, required_default=True):
    """Run one dataset's declared check, recording the outcome."""
    spec = dataset.check
    kind = spec.get("kind")
    module = spec.get("needs_module")
    # The credential-gated kinds report a missing credential before a missing
    # library: "set UCSD_NT_S3_ACCESS_KEY" is the actionable message, and the
    # library only matters once you have one. Their bodies raise on ImportError.
    gated = kind in ("s3-list", "sql-tables")
    available = have(module) if module and not gated else True
    required = required_default and available

    with check(spec["label"], required=required) as c:
        if module and not gated and not available:
            raise RuntimeError(f"skipped: {spec['needs_hint']}")

        if kind == "osdf-listing":
            from pelicanfs.core import OSDFFileSystem
            path = dataset.resolve()
            objects = OSDFFileSystem().ls(path)
            assert objects, f"{path} listed empty"
            c.note = f"{len(objects)} objects in {path}"

        elif kind == "http-head":
            url = spec.get("url") or dataset.url()
            status, headers = http_head(url)
            c.note = f"HTTP {status}, {spec.get('note_suffix') or human_size(headers)}"

        elif kind == "parquet-magic":
            # This endpoint answers HEAD with 405 and ignores Range on a GET, so
            # read just the 4-byte Parquet magic off the front and drop the rest
            # rather than pulling ~4 MiB.
            head = http_first_bytes(dataset.url(), 4)
            assert head == b"PAR1", f"expected a Parquet file, got {head!r}"
            c.note = "PAR1 magic ok"

        elif kind == "bolt":
            from neo4j import GraphDatabase
            uri = dataset.url()
            db = GraphDatabase.driver(uri, auth=None)
            try:
                db.verify_connectivity()
            finally:
                db.close()
            c.note = uri

        elif kind == "http-magic":
            # The public-coordinate analogue of `magic`: prove the object is really
            # there and is really what it claims, without pulling the whole file. A 200
            # on its own would pass against an error page.
            url = dataset.url()
            magic = bytes.fromhex(spec["magic"])
            head = http_first_bytes(url, len(magic))
            assert head.startswith(magic), f"expected {magic.hex()}, got {head.hex()}"
            c.note = f"magic ok, {url.rsplit('/', 1)[-1]}"

        elif kind in ("magic", "readable"):
            magic = bytes.fromhex(spec["magic"]) if kind == "magic" else None
            head = ceph_first_bytes(dataset.resolve(), len(magic) if magic else 8)
            if magic:
                assert head.startswith(magic), f"expected {magic!r}, got {head!r}"
            c.note = "magic ok" if magic else "readable"

        elif kind == "s3-list":
            access = os.environ.get(dataset.credentials[0])
            secret = os.environ.get(dataset.credentials[1])
            if not (access and secret):
                raise RuntimeError(f"skipped: {spec['skip_hint']}")
            try:
                import boto3
                from botocore.config import Config
            except ImportError:
                raise RuntimeError(f"skipped: {spec['needs_hint']}") from None
            s3 = boto3.client(
                "s3",
                endpoint_url=dataset.access["endpoint"],
                aws_access_key_id=access,
                aws_secret_access_key=secret,
                config=Config(
                    signature_version=dataset.access["signature_version"],
                    s3={"addressing_style": dataset.access["addressing_style"]},
                ),
            )
            prefix = dataset.resolve()
            listing = s3.list_objects_v2(
                Bucket=dataset.access["bucket"], Prefix=prefix, MaxKeys=5
            )
            assert listing.get("KeyCount"), f"{prefix} listed empty"
            c.note = f"{listing['KeyCount']}+ objects under {prefix}"

        elif kind == "sql-tables":
            dsn = os.environ.get(dataset.credentials[0])
            if not dsn:
                raise RuntimeError(f"skipped: {spec['skip_hint']}")
            try:
                from sqlalchemy import create_engine, text
            except ImportError:
                raise RuntimeError(f"skipped: {spec['needs_hint']}") from None
            engine = create_engine(dsn)
            schema = dataset.access["schema_name"]
            with engine.connect() as conn:
                tables = conn.execute(
                    text("SELECT table_name FROM information_schema.tables "
                         "WHERE table_schema = :schema ORDER BY table_name"),
                    {"schema": schema},
                ).scalars().all()
            assert tables, f"schema {schema} has no tables"
            # The DSN is never printed -- it carries a password.
            c.note = f"{len(tables)} tables: {', '.join(tables)}"

        else:
            raise RuntimeError(f"unknown check kind {kind!r} in {dataset.path}")


def in_cluster():
    """True when the in-cluster Ceph hostname resolves, i.e. we are running on NRP.

    Cached on the function because every Ceph dataset asks the same question. Off
    cluster, a Ceph dataset being unreachable is the expected result and must not fail
    the run -- that is the same rule the sectioned run applies by declaring the whole
    Ceph section not-required.
    """
    if not hasattr(in_cluster, "_answer"):
        host = CEPH.split("//", 1)[1]
        try:
            socket.getaddrinfo(host, 80)
            in_cluster._answer = True
        except socket.gaierror:
            in_cluster._answer = False
    return in_cluster._answer


def _describe(dataset):
    """A human address for a transport with no URL form, e.g. Postgres."""
    access = dataset.access
    if dataset.transport == "postgres":
        return f"{access['service']}:{access['port']} schema {access['schema_name']}"
    return f"({dataset.transport})"


def list_registry(datasets):
    """`--list`: what would be checked, and where each coordinate resolves to."""
    for section in ("external", "ceph", "credentialed"):
        for dataset in nids_registry.checks_in_order(datasets, section):
            try:
                where = dataset.check.get("url") or dataset.url() or _describe(dataset)
            except KeyError:
                where = "(needs an assignment pin)"
            print(f"{section:12} {dataset.id:26} {where}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true",
                        help="print the registry's checks and their resolved paths, run nothing")
    parser.add_argument("--assignment", metavar="CODE",
                        help="check only the datasets one assignment reads (e.g. BGP)")
    parser.add_argument("--release", default="r1", choices=("r1", "all"),
                        help="which release to check: r1 (default) is the modules that need "
                             "only publicly downloadable data; all checks every dataset")
    args = parser.parse_args(argv)

    datasets = nids_registry.load_datasets()
    all_assignments = nids_registry.load_assignments()

    if args.release != "all" and not args.assignment:
        # Scope to what the release actually reads. Out-of-scope datasets are not
        # attempted at all rather than attempted-and-skipped: an instructor's first run
        # must not print red for datasets they will never touch.
        in_release = nids_registry.datasets_in_release(datasets, all_assignments, args.release)
        kept = {d.id for d in in_release}
        dropped = sorted(set(datasets) - kept)
        datasets = {i: d for i, d in datasets.items() if i in kept}
        modules = sorted(c for c, a in all_assignments.items() if a.release == args.release)
        print(f"release {args.release}: {', '.join(modules)} "
              f"-- {len(kept)} datasets, {len(dropped)} out of scope\n")

    if args.assignment:
        assignments = all_assignments
        code = args.assignment.upper()
        if code not in assignments:
            known = ", ".join(sorted(assignments)) or "none -- assignments/registry.toml is missing"
            raise SystemExit(f"unknown assignment {code!r}. Known: {known}")
        wanted = nids_registry.datasets_for(datasets, assignments, code)
        if args.list:
            for dataset, pins, required in wanted:
                where = dataset.url(**pins) or _describe(dataset)
                print(f"{code:12} {dataset.id:26} {where}")
            return 0
        print(f"--- {code}: {len(wanted)} datasets ---\n")
        for dataset, pins, required in wanted:
            # Off cluster, Ceph is unreachable by design and credential-gated datasets
            # are opt-in; neither is this assignment being broken.
            if not dataset.reachable_offsite and not in_cluster():
                required = False
            if dataset.credentials:
                required = False
            if pins:
                # An assignment pin overrides the dataset default, so a check run
                # this way tests the exact coordinate that assignment reads.
                dataset.defaults = {**dataset.defaults, **pins}
            run_check(dataset, required_default=required)
        return report()

    if args.list:
        return list_registry(datasets)

    print("--- external: reachable from anywhere ---\n")
    for dataset in nids_registry.checks_in_order(datasets, "external"):
        run_check(dataset)

    print("\n--- in-cluster Ceph: expected to fail outside NRP ---\n")
    for dataset in nids_registry.checks_in_order(datasets, "ceph"):
        run_check(dataset, required_default=False)

    print("\n--- credential-gated: skipped unless configured ---\n")
    for dataset in nids_registry.checks_in_order(datasets, "credentialed"):
        run_check(dataset, required_default=False)

    return report()


if __name__ == "__main__":
    sys.exit(main())
