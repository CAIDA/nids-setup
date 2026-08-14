# CAIDA AS Customer Cone (ppdc-ases)

CAIDA's inferred customer cones: for each AS, the set of ASes reachable through it as a customer. One
bz2 text file per monthly serial, mirrored on in-cluster Ceph.

- **Used by:** ASN, BGP
- **Produced by:** CAIDA
- **Served from:** In-cluster only (Ceph)
- **Public version usable:** Yes — the same file is published openly; NIDS reads a Ceph copy
- **Setup:** ❌ required, procedure not documented — see below
- **Credentials:** none
- **Time-sensitive:** Yes — the filename encodes a `YYYYMMDD` serial
- **Licence / governance:** open

## Access

Plain HTTP GET against the in-cluster Ceph RGW:

```python
CEPH = "http://rook-ceph-rgw-nautiluss3.rook"
url = f"{CEPH}/caida/as-relationships/20260501.ppdc-ases.txt.bz2"
```

- `rook-ceph-rgw-nautiluss3.rook` resolves **only inside the NRP cluster**. From a laptop this fails
  at DNS, which is expected and not a fault.
- Format: bz2-compressed text, one line per AS — `AS <space-separated cone members>` — with `#`
  comments.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| ASN | `caida/as-relationships/20260501.ppdc-ases.txt.bz2` | `nids-asn-introduction-key/00-environment-check.ipynb:181` |
| BGP | `caida/as-relationships/20260501.ppdc-ases.txt.bz2` | `nids-bgp-control-plane-key/00-environment-check.ipynb:184` |

Both assignments use the same May 2026 serial.

Note a divergence worth knowing about: ASN's student-facing `Datasets.md` instructs a **manual browser
download** of `20260501.ppdc-ases.txt.bz2` into a local `data/` directory, while the notebooks fetch
it from Ceph. Both routes reach the same file.

## Validate

Range-GET the first 3 bytes and assert the bzip2 magic `b"BZh"`. Cheap, and it proves the gateway is
both resolvable and actually serving object bytes rather than an error page.

## Setup

**Step-by-step instructions are required here and do not exist.** The object is on Ceph and the
assignments read it, but no repo records how it got there. This section records what is known so
whoever has the answer can complete it; nothing here should be treated as a procedure.

Known:

- **Upstream source:** `https://publicdata.caida.org/datasets/as-relationships/serial-1/`, which
  publishes `<YYYYMMDD>.ppdc-ases.txt.bz2` monthly. **[unverified]** as the actual mirror source.
- **Target path:** `caida/as-relationships/<YYYYMMDD>.ppdc-ases.txt.bz2` in the Ceph `caida` bucket,
  served by `rook-ceph-rgw-nautiluss3.rook`.
- **Artifact shape:** copied verbatim — the mirrored filename and bz2 format match upstream, so no
  transformation appears to be involved. **[unverified]**

Must be recovered:

- Who or what uploads to the Ceph `caida` bucket, with which credentials and which tool. No upload
  script, bucket policy, or S3 credential for this bucket exists anywhere in the NIDS repositories.
- Whether the copy is manual or scheduled, and on what cadence relative to CAIDA's monthly release.
- Whether older serials are retained or replaced.

### Refreshing to a newer snapshot

Blocked on the above. When a new serial is needed, the filename is the only thing that changes:
update `AS_CONE` in `nids-asn-introduction-key/00-environment-check.ipynb` and
`nids-bgp-control-plane-key/00-environment-check.ipynb`, plus the corresponding key notebooks and this
file's values table.

## See also

- `nids-asn-introduction/Datasets.md`, `nids-bgp-control-plane/Datasets.md`
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the Ceph
  egress row
