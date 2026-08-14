# RouteViews prefix2as

CAIDA's prefix-to-AS mappings derived from RouteViews BGP data: for each announced prefix, the AS
that originates it. Mirrored on in-cluster Ceph, one gzip file per day.

- **Used by:** IRR
- **Produced by:** CAIDA — derived from RouteViews
- **Served from:** In-cluster only (Ceph)
- **Public version usable:** Yes — the same files are published openly; NIDS reads a Ceph copy
- **Setup:** ❌ required, procedure not documented — see below
- **Credentials:** none
- **Time-sensitive:** Yes — the path encodes `YYYY/MM/` and a `YYYYMMDD` in the filename
- **Licence / governance:** open

## Access

Plain HTTP GET against the in-cluster Ceph RGW:

```python
CEPH = "http://rook-ceph-rgw-nautiluss3.rook"
PREFIX2AS_BASE = f"{CEPH}/caida/routing/routeviews-prefix2as"

url = (f"{PREFIX2AS_BASE}/{d:%Y}/{d:%m}/"
       f"routeviews-rv2-{d:%Y%m%d}-1200.pfx2as.gz")
```

- `rook-ceph-rgw-nautiluss3.rook` resolves **only inside the NRP cluster**.
- Format: gzip-compressed text, `prefix/len AS` per line.
- The `-1200` in the filename is a fixed collection hour, not a variable. CAIDA publishes more than
  one file per day upstream; the mirror path used here always takes the 12:00 one.
- The year and month appear **twice** — once as directory components, once inside the filename. Both
  must agree or the object 404s.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| IRR (reachability probe) | `caida/routing/routeviews-prefix2as/2023/03/routeviews-rv2-20230301-1200.pfx2as.gz` | `nids-irr-rpki-whois-key/00-environment-check.ipynb:182` |
| IRR (series) | one file per snapshot date, built by the same pattern | `nids-irr-rpki-whois-key/nids-irr-rpki-whois-key.ipynb:258-263` |

## Validate

Range-GET the first bytes and assert the gzip magic.

## Setup

**Step-by-step instructions are required here and do not exist.** The mirroring step is undocumented,
though this is the most mechanical of the Ceph datasets — upstream layout and mirror layout appear to
match closely.

Known:

- **Upstream source:** `https://publicdata.caida.org/datasets/routing/routeviews-prefix2as/`, which
  publishes `<YYYY>/<MM>/routeviews-rv2-<YYYYMMDD>-<HHMM>.pfx2as.gz`. **[unverified]** as the actual
  mirror source, though the path structure matches.
- **Target path:** `caida/routing/routeviews-prefix2as/<YYYY>/<MM>/routeviews-rv2-<YYYYMMDD>-1200.pfx2as.gz`.
- **Artifact shape:** copied verbatim; the directory layout and filename convention are upstream's.

Must be recovered:

- Whether the mirror carries every upstream file or only the 12:00 one per day, and whether the date
  range is bounded.
- Who uploads to the Ceph `caida` bucket, with which credentials and tool, and on what cadence.

### Refreshing to a newer snapshot

Blocked on the above. Because the URL is fully derived from a date, no code change is needed to move
to a different day that is already mirrored — only the snapshot dates in
`nids-irr-rpki-whois-key/nids-irr-rpki-whois-key.ipynb:121-125` and the probe date in its environment
check.

## See also

- `nids-irr-rpki-whois/Datasets.md`
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the Ceph
  egress row
