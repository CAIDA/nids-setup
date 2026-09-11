# CAIDA AS-to-Organization (as2org)

CAIDA's mapping from AS numbers to the organisations that operate them, used to group ASes by
operator and to attach a country to an AS. Mirrored on in-cluster Ceph as a single JSONL file.

- **Used by:** ASN, BGP
- **Produced by:** CAIDA
- **Served from:** In-cluster only (Ceph)
- **Public version usable:** Yes via CAIDA's API, but the Ceph object is a **NIDS-specific flattened
  JSONL**, not a file published upstream in this form
- **Setup:** ❌ required, procedure not documented — see below
- **Credentials:** none
- **Time-sensitive:** No — the filename is stable and undated
- **Licence / governance:** open

## Access

Plain HTTP GET against the in-cluster Ceph RGW:

```python
CEPH = "http://rook-ceph-rgw-nautiluss3.rook"
url = f"{CEPH}/caida/as2org/as2org.jsonl"
```

- `rook-ceph-rgw-nautiluss3.rook` resolves **only inside the NRP cluster**.
- Format: JSON Lines — one JSON object per line, so it can be streamed without loading the whole file.
  Fields follow CAIDA's as2org model (`orgId`, `orgName`, `country`, `source`, `members`, `changed`,
  `date`).
- The filename carries **no date**. That makes the path stable, but it also means there is no way to
  tell from the path which upstream release the file was built from.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| ASN | `caida/as2org/as2org.jsonl` | `nids-asn-introduction-key/00-environment-check.ipynb:180` |
| BGP | `caida/as2org/as2org.jsonl` | `nids-bgp-control-plane-key/00-environment-check.ipynb:183` |

This object is also what [notebooks/test.ipynb](../../notebooks/test.ipynb) uses to prove the Ceph
gateway works at all — it is read by two of the assignments and is the smallest such proof.

## Validate

Range-GET the first 8192 bytes and `json.loads` the first line. Unlike a magic-byte check this
confirms the object is actually well-formed JSONL, which matters because it is a derived artifact
rather than a verbatim upstream copy.

## Setup

**Step-by-step instructions are required here and do not exist.** This is the most consequential ❌ of
the Ceph set, because the object is not a verbatim mirror: `as2org.jsonl` is a flattened
NIDS-specific rendering of CAIDA's as2org data, so reproducing it requires knowing both the source and
the transformation.

Known:

- **Upstream source:** CAIDA's as2org dataset, available as a paginated API at
  `https://api.data.caida.org/as2org/v1/orgs/` and as periodic bulk files from
  `https://publicdata.caida.org/datasets/as-organizations/`. **Not established:** which of the two
  the Ceph object was built from.
- **Target path:** `caida/as2org/as2org.jsonl` in the Ceph `caida` bucket.
- **Artifact shape:** JSON Lines, one organisation record per line.
- **Partial lead:** `nids-overview/datasets.md` refers to pagination being "handled by provided
  `org-download.py`", and an `orgs-download.py` exists under
  `nids-asn-introduction-key/temp/scripts/`. **Not established:** whether either produced this
  exact file — check them before writing a procedure.

Must be recovered:

- The transformation from upstream to `as2org.jsonl`: which fields, what ordering, whether records are
  filtered.
- Which upstream release the current object corresponds to. Nothing in the path or (as far as is
  known) the file records it.
- Who uploads to the Ceph `caida` bucket, with which credentials and tool, and on what cadence.

### Refreshing to a newer snapshot

Blocked on the above, and harder than the dated datasets: because the filename is stable, a refresh
**overwrites in place**. Any figure a student computed before the swap silently stops being
reproducible, with nothing in the path to signal that it changed. Consider adding a dated filename
when the procedure is documented.

## See also

- `nids-asn-introduction/Datasets.md`, `nids-bgp-control-plane/Datasets.md`
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the Ceph
  egress row
