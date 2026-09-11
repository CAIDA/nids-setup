# CAIDA IRR WHOIS dumps

Snapshots of Internet Routing Registry databases, collected by CAIDA from 16 IRR sources and mirrored
on in-cluster Ceph under a dated directory. Used to compare registry-declared route objects against
observed BGP.

- **Used by:** IRR
- **Produced by:** CAIDA — dumps collected from 16 external IRRs
- **Served from:** In-cluster only (Ceph)
- **Public version usable:** The individual IRRs publish their own dumps; this **collection**, snapshotted
  on one date across all 16, is CAIDA's
- **Setup:** ❌ required, procedure not documented — see below
- **Credentials:** none
- **Time-sensitive:** Yes — the path encodes a `YYYY-MM-DD` snapshot date
- **Licence / governance:** open

## Access

Plain HTTP GET against the in-cluster Ceph RGW. The mirror preserves the upstream FTP directory
layout, so every object sits under a `ftp.radb.net/radb/dbase/` path regardless of which registry it
came from:

```python
CEPH = "http://rook-ceph-rgw-nautiluss3.rook"
IRR_BASE = f"{CEPH}/caida/routing/irr_dumps"
url = f"{IRR_BASE}/{snapshot_date}/ftp.radb.net/radb/dbase/{source}.db.gz"
```

- `rook-ceph-rgw-nautiluss3.rook` resolves **only inside the NRP cluster**.
- Format: gzip-compressed RPSL text.
- The `ftp.radb.net/radb/dbase/` path segment is part of the mirror's layout for **all** sources, not
  just RADB. Do not try to derive a per-registry hostname from it.

### The 16 sources

`altdb`, `arin`, `bboi`, `bell`, `canarie`, `host`, `jpirr`, `level3`, `nestegg`, `nttcom`,
`openface`, `panix`, `radb`, `reach`, `rgnet`, `tc`

16 files mapping 1:1 onto 16 logical sources.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| IRR (reachability probe) | `caida/routing/irr_dumps/2023-03-01/ftp.radb.net/radb/dbase/radb.db.gz` | `nids-irr-rpki-whois-key/00-environment-check.ipynb:180-181` |
| IRR (discovery) | snapshot `2023-12-07` | `nids-irr-rpki-whois-key/nids-irr-rpki-whois-key.ipynb:121-125` |
| IRR (monthly series) | first of each month, Jan–Jun 2023 | `nids-irr-rpki-whois-key/nids-irr-rpki-whois-key.ipynb:121-125` |

## Validate

Range-GET the first bytes of one source's dump and assert the gzip magic. `radb.db.gz` at the probe
date is the sample the assignment's own check uses.

## Setup

**Step-by-step instructions are required here and do not exist.** Both the collection step (fetching
16 registries on a common date) and the Ceph upload step are undocumented.

Known:

- **Upstream sources:** each of the 16 IRRs publishes its own database dump over FTP/HTTPS; RADB's is
  at `ftp.radb.net/radb/dbase/`. **Not established:** whether CAIDA fetches each registry
  directly or obtains a pre-assembled collection.
- **Target path:** `caida/routing/irr_dumps/<YYYY-MM-DD>/ftp.radb.net/radb/dbase/<source>.db.gz`.
- **Artifact shape:** gzip RPSL, apparently verbatim from upstream, re-filed under a single dated
  directory that mirrors RADB's FTP layout for every source.

Must be recovered:

- Whether a CAIDA public path publishes these dumps (unlike the cone and prefix2as datasets, no
  `publicdata.caida.org` path for the IRR dump collection was found — do not assume one exists).
- The collection procedure: which 16 URLs, fetched in what order, and how "one snapshot date" is
  defined when the registries publish on their own schedules.
- Why all sources are filed under a RADB-shaped path, and whether that is intentional or an artefact
  of how the mirror was first built.
- Who uploads to the Ceph `caida` bucket, with which credentials and tool, and on what cadence.

### Refreshing to a newer snapshot

Blocked on the above. A refresh means a new dated directory with all 16 sources, then updating
`SAMPLE_DATE` / `IRR_DISCOVERY_DATE` / the monthly snapshot list in
`nids-irr-rpki-whois-key/nids-irr-rpki-whois-key.ipynb:121-125` and its environment check.

## See also

- `nids-irr-rpki-whois/Datasets.md`
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the Ceph
  egress row
