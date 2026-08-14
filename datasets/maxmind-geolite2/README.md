# MaxMind GeoLite2-City (Ceph mirror)

MaxMind's free city-level IP geolocation database, in MMDB form, mirrored on in-cluster Ceph. Used to
attach a country and city to telescope source addresses.

- **Used by:** TELESCOPE
- **Produced by:** External — MaxMind, CAIDA-mirrored
- **Served from:** In-cluster only (Ceph)
- **Public version usable:** **No, not directly** — MaxMind gates GeoLite2 behind a free account and a
  licence key. The mirror exists precisely so the assignment needs neither.
- **Setup:** ❌ required, procedure not documented — see below
- **Credentials:** none, **because** of the mirror
- **Time-sensitive:** Yes — the filename encodes a `YYYY-MM-DD` build date
- **Licence / governance:** upstream is licence-gated (MaxMind GeoLite2 EULA). Whether the mirror is
  licensed to re-serve it is an open question. **[unverified]**

## Access

Plain HTTP GET against the in-cluster Ceph RGW:

```python
CEPH = "http://rook-ceph-rgw-nautiluss3.rook"
url = f"{CEPH}/caida/geolocation/maxmind/2026-06-24.GeoLite2-City.mmdb.gz"
```

- `rook-ceph-rgw-nautiluss3.rook` resolves **only inside the NRP cluster**.
- Format: gzip-compressed MMDB, read with `geoip2` / `maxminddb` after decompression.
- **No MaxMind account or licence key is needed** to use the assignment. This is worth stating
  explicitly because every MaxMind tutorial online begins by telling you to sign up.
- The date is a **prefix**, not a suffix: `2026-06-24.GeoLite2-City.mmdb.gz`.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| TELESCOPE | `caida/geolocation/maxmind/2026-06-24.GeoLite2-City.mmdb.gz` | `nids-telescope-traffic-key/00-environment-check.ipynb:181` |

MaxMind rebuilds GeoLite2 weekly, so a pinned build date is what makes a student's geolocation
results reproducible.

## Validate

Range-GET the first bytes and assert the gzip magic, plus an HTTP HEAD for the size.

## Setup

**Step-by-step instructions are required here and do not exist.** Unlike the other Ceph datasets, the
gap here is not only operational but legal: the upstream is licence-gated, so the mirroring step
involves credentials *and* a redistribution question.

Known:

- **Upstream source:** `https://dev.maxmind.com/geoip/geolite2-free-geolocation-data`. Downloads
  require a MaxMind account and a licence key, and are served as a dated tarball containing the MMDB.
- **Target path:** `caida/geolocation/maxmind/<YYYY-MM-DD>.GeoLite2-City.mmdb.gz`.
- **Artifact shape:** the `.mmdb` extracted from MaxMind's tarball, re-gzipped on its own and renamed
  with the build date as a filename prefix. So there **is** a transformation here, not a verbatim copy.
  **[unverified]** in detail.

Must be recovered:

- **Whose MaxMind account and licence key** the download uses, and where that key is held.
- **Whether the GeoLite2 EULA permits re-serving the database** to a class from a CAIDA-operated
  store. This is the question to answer before the mirror is relied on further; it is tracked in
  [DESIGN.md](../../DESIGN.md#open-questions).
- The extraction and renaming steps, exactly enough to reproduce the current filename convention.
- Who uploads to the Ceph `caida` bucket, with which credentials and tool, and whether the weekly
  upstream rebuild is tracked at all.

Note that `nids-geolocation`, when it lands, will need MaxMind GeoLite2 **CSVs** (blocks and
locations) rather than the MMDB — a different artifact from the same upstream, which will need its own
directory rather than an extra path here.

### Refreshing to a newer snapshot

Blocked on the above. A refresh changes only `GEOIP_DB` in
`nids-telescope-traffic-key/00-environment-check.ipynb:181` and the corresponding constant in
`flow_analysis.ipynb`, plus this file's values table — but it also silently changes every geolocation
result, so it should be treated as a deliberate re-pinning rather than routine maintenance.

## See also

- `nids-telescope-traffic/Datasets.md`
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the Ceph
  egress row
