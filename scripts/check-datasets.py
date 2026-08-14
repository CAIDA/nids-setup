#!/usr/bin/env python3
"""Check that every NIDS dataset is reachable from outside the NRP cluster.

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

import importlib
import os
import socket
import sys
import urllib.error
import urllib.request


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


HAVE_PELICANFS = have("pelicanfs.core")
HAVE_NEO4J = have("neo4j")

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


# --- dataset coordinates -------------------------------------------------------
# Every value below is the one an assignment actually uses today. When one of
# these goes stale, the matching datasets/<name>/README.md values table is the
# other place that needs updating.

OSDF_RIB_DIR = "/routeviews/route-views3/bgpdata/2026.05/RIBS"          # BGP
RPKI_URL = "https://ftp.ripe.net/ripe/rpki/afrinic.tal/2023/03/01/roas.csv.xz"
OI_ENDPOINT = "https://object.openintel.nl"
OI_BUCKET_URL = f"{OI_ENDPOINT}/openintel-public"
ANYCAST_URL = "https://manycast.net/api/v1/export/IPv4-latest.parquet"
IYP_URI = "neo4j://iyp-bolt.ihr.live:7687"

AS_CONE = "caida/as-relationships/20260501.ppdc-ases.txt.bz2"           # ASN, BGP
AS2ORG = "caida/as2org/as2org.jsonl"                                    # ASN, BGP
IRR_OBJECT = "caida/routing/irr_dumps/2023-03-01/ftp.radb.net/radb/dbase/radb.db.gz"
PREFIX2AS_OBJECT = "caida/routing/routeviews-prefix2as/2023/03/routeviews-rv2-20230301-1200.pfx2as.gz"
PCAP_A = "caida/ucsd-nt/sample_062026/ucsd-nt-sub.1782463980.anon.pcap.gz"
GEOIP_DB = "caida/geolocation/maxmind/2026-06-24.GeoLite2-City.mmdb.gz"

UCSDNT_ENDPOINT = "https://hermes.caida.org"
UCSDNT_BUCKET = "telescope-ucsdnt-avro-flowtuple-v4-2026"
UCSDNT_PREFIX = "datasource=ucsd-nt/year=2026/month=02/day=14/"


def main():
    print("--- external: reachable from anywhere ---\n")

    with check("osdf: routeviews rib listing (BGP, TELESCOPE)", required=HAVE_PELICANFS) as c:
        if not HAVE_PELICANFS:
            raise RuntimeError("skipped: pip install pelicanfs")
        from pelicanfs.core import OSDFFileSystem
        objects = OSDFFileSystem().ls(OSDF_RIB_DIR)
        assert objects, f"{OSDF_RIB_DIR} listed empty"
        c.note = f"{len(objects)} objects in {OSDF_RIB_DIR}"

    with check("ftp.ripe.net: rpki roas (IRR)") as c:
        # The only assignment reaching this host. A namespace that allows CAIDA
        # and OSDF but not RIPE fails here and nowhere else.
        status, headers = http_head(RPKI_URL)
        c.note = f"HTTP {status}, {human_size(headers)}"

    with check("manycast.net: anycast census (DNS)") as c:
        # This endpoint answers HEAD with 405, and ignores Range on a GET -- so
        # read just the 4-byte Parquet magic off the front and drop the rest
        # rather than pulling ~4 MiB.
        head = http_first_bytes(ANYCAST_URL, 4)
        assert head == b"PAR1", f"expected a Parquet file, got {head!r}"
        c.note = "PAR1 magic ok"

    with check("object.openintel.nl: bucket is anonymously readable (DNS)") as c:
        # HEAD on the S3 root is 403 by design; the bucket URL is the smallest
        # request that proves anonymous access actually works. A real Parquet
        # read needs Spark and the S3A jars -- that is the DNS assignment's own
        # check, not this one.
        status, _ = http_head(OI_BUCKET_URL)
        c.note = f"HTTP {status}, openintel-public"

    with check("iyp: public bolt endpoint (IYP)", required=HAVE_NEO4J) as c:
        if not HAVE_NEO4J:
            raise RuntimeError("skipped: pip install neo4j")
        from neo4j import GraphDatabase
        db = GraphDatabase.driver(IYP_URI, auth=None)
        try:
            db.verify_connectivity()
        finally:
            db.close()
        c.note = IYP_URI

    print("\n--- in-cluster Ceph: expected to fail outside NRP ---\n")

    for label, path, magic in [
        ("ceph: customer cone (ASN, BGP)", AS_CONE, b"BZh"),
        ("ceph: as2org (ASN, BGP)", AS2ORG, None),
        ("ceph: irr whois dumps (IRR)", IRR_OBJECT, b"\x1f\x8b"),
        ("ceph: routeviews prefix2as (IRR)", PREFIX2AS_OBJECT, b"\x1f\x8b"),
        ("ceph: ucsd-nt pcap sample (TELESCOPE)", PCAP_A, b"\x1f\x8b"),
        ("ceph: maxmind geolite2 (TELESCOPE)", GEOIP_DB, b"\x1f\x8b"),
    ]:
        with check(label, required=False) as c:
            head = ceph_first_bytes(path, len(magic) if magic else 8)
            if magic:
                assert head.startswith(magic), f"expected {magic!r}, got {head!r}"
            c.note = "magic ok" if magic else "readable"

    print("\n--- credential-gated: skipped unless configured ---\n")

    with check("expanse: ucsd-nt flowtuple bucket (UCSDNT)", required=False) as c:
        access = os.environ.get("UCSD_NT_S3_ACCESS_KEY")
        secret = os.environ.get("UCSD_NT_S3_SECRET_KEY")
        if not (access and secret):
            raise RuntimeError(
                "skipped: set UCSD_NT_S3_ACCESS_KEY and UCSD_NT_S3_SECRET_KEY "
                "(see datasets/ucsdnt-expanse-flowtuple/)"
            )
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise RuntimeError("skipped: pip install boto3") from None
        s3 = boto3.client(
            "s3",
            endpoint_url=UCSDNT_ENDPOINT,
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        listing = s3.list_objects_v2(Bucket=UCSDNT_BUCKET, Prefix=UCSDNT_PREFIX, MaxKeys=5)
        assert listing.get("KeyCount"), f"{UCSDNT_PREFIX} listed empty"
        c.note = f"{listing['KeyCount']}+ objects under {UCSDNT_PREFIX}"

    with check("itdk: postgres caida_itdk schema (ITDK)", required=False) as c:
        dsn = os.environ.get("ITDK_READ_DSN")
        if not dsn:
            raise RuntimeError(
                "skipped: set ITDK_READ_DSN and port-forward postgres-service "
                "(see datasets/itdk-postgres/)"
            )
        try:
            from sqlalchemy import create_engine, text
        except ImportError:
            raise RuntimeError("skipped: pip install sqlalchemy psycopg2-binary") from None
        engine = create_engine(dsn)
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT table_name FROM information_schema.tables "
                     "WHERE table_schema = 'caida_itdk' ORDER BY table_name")
            ).scalars().all()
        assert tables, "schema caida_itdk has no tables"
        # The DSN is never printed -- it carries a password.
        c.note = f"{len(tables)} tables: {', '.join(tables)}"

    return report()


if __name__ == "__main__":
    sys.exit(main())
