# UCSD Network Telescope PCAP samples

Two short anonymized packet captures from the UCSD Network Telescope, taken seven minutes apart so
that a traffic surge is visible between them. Mirrored on in-cluster Ceph.

- **Used by:** TELESCOPE
- **Produced by:** CAIDA — UCSD Network Telescope
- **Served from:** In-cluster only (Ceph)
- **Public version usable:** **No** — these are anonymized derivatives prepared for the assignment;
  the raw telescope captures are AUA/DUA-governed and stay on SDSC Expanse
- **Setup:** ❌ required, procedure not documented — see below
- **Credentials:** none (for the anonymized samples)
- **Time-sensitive:** Yes — the directory and both filenames encode fixed dates/epochs
- **Licence / governance:** derived from AUA/DUA-governed data; the anonymized samples are served
  openly from Ceph. **[unverified]** which terms apply to the derivatives.

## Access

Plain HTTP GET against the in-cluster Ceph RGW:

```python
CEPH = "http://rook-ceph-rgw-nautiluss3.rook"
PCAP_A = f"{CEPH}/caida/ucsd-nt/sample_062026/ucsd-nt-sub.1782463980.anon.pcap.gz"
PCAP_B = f"{CEPH}/caida/ucsd-nt/sample_062026/ucsd-nt-sub.1782464400.anon.pcap.gz"
```

- `rook-ceph-rgw-nautiluss3.rook` resolves **only inside the NRP cluster**.
- Format: gzip-compressed pcap, parsed with `dpkt`.
- **The directory serial is `MMYYYY`, not `YYYYMM`.** `sample_062026` is June 2026. This reads
  backwards from every other dated path in this repo and is easy to mistype.
- The two filename components are **Unix epochs**, 420 seconds apart: `1782463980` and `1782464400`,
  corresponding to 2026-06-26 08:53 and 09:00 UTC. The surge the assignment investigates appears in
  the second capture.
- TELESCOPE has a hard 16 GiB memory floor (24 GiB recommended) and processes one capture at a time.
  That is a spawner-profile concern, enforced by the assignment's own environment check, not a
  property of this dataset.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| TELESCOPE | `caida/ucsd-nt/sample_062026/ucsd-nt-sub.1782463980.anon.pcap.gz` | `nids-telescope-traffic-key/00-environment-check.ipynb:179` |
| TELESCOPE | `caida/ucsd-nt/sample_062026/ucsd-nt-sub.1782464400.anon.pcap.gz` | `nids-telescope-traffic-key/00-environment-check.ipynb:180` |

## Validate

Range-GET the first bytes of the first capture and assert the gzip magic; HTTP HEAD the second. Both
objects must be present — the assignment's entire comparison depends on having the pair.

## Setup

**Step-by-step instructions are required here and do not exist**, and this is the ❌ with the highest
stakes: the samples are derived from governed data, so reproducing them is not merely a copy but an
anonymization step whose parameters are unrecorded.

Known:

- **Upstream source:** the UCSD Network Telescope raw capture archive, held on SDSC Expanse under
  AUA/DUA terms. See [ucsdnt-expanse-flowtuple](../ucsdnt-expanse-flowtuple/) for the credentialed
  path to telescope data.
- **Target path:** `caida/ucsd-nt/sample_<MMYYYY>/ucsd-nt-sub.<epoch>.anon.pcap.gz`.
- **Artifact shape:** a time-bounded subset (`-sub`) of a capture, anonymized (`.anon`), gzip-compressed.
  The two epochs are 420 s apart and were chosen so a real surge falls between them.

Must be recovered:

- **The anonymization procedure and its parameters** — which tool, which key or prefix-preserving
  scheme, and whether the key is retained. Without this the samples cannot be regenerated, and no
  equivalent samples can be made from a different date.
- How the capture window and the two epochs were selected, and how long each capture runs.
- Whether releasing anonymized derivatives openly is covered by the telescope's AUA/DUA, and who
  approved it.
- Who uploads to the Ceph `caida` bucket, with which credentials and tool.

### Refreshing to a newer snapshot

Not a refresh in the usual sense. These samples are pinned teaching material chosen for a specific
event; regenerating them for a new period means re-selecting an interesting window and re-running an
anonymization that is currently undocumented. Treat them as fixed until the procedure is recovered.

## See also

- `nids-telescope-traffic/Datasets.md`, `nids-telescope-traffic/Dpkt.md`
- [ucsdnt-expanse-flowtuple](../ucsdnt-expanse-flowtuple/) — the other, credentialed telescope dataset
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the Ceph
  egress row
