# Anycast Census (LACeS / manycast.net)

A census of which IPv4 prefixes are anycast, published as a single always-current Parquet file. Used
to tell whether a name server's address is anycast.

- **Used by:** DNS
- **Produced by:** External — LACeS / manycast.net
- **Served from:** Both — external egress to `manycast.net`
- **Public version usable:** Yes — read directly
- **Setup:** none needed
- **Credentials:** none
- **Time-sensitive:** Low — the URL is `IPv4-latest`, with no date to keep current
- **Licence / governance:** open

## Access

A single HTTPS URL:

```python
ANYCAST_URL = "https://manycast.net/api/v1/export/IPv4-latest.parquet"
```

Note the read pattern: the assignment **downloads the file to local disk first**, then reads it with
Spark from there — it does not read the URL through Spark.

```python
import requests
ANYCAST_LOCAL = "/tmp/anycast-census.parquet"
with open(ANYCAST_LOCAL, "wb") as fh:
    fh.write(requests.get(ANYCAST_URL, timeout=60).content)
df = spark.read.parquet(ANYCAST_LOCAL)
```

- **The live schema differs from the published documentation.** The file carries per-probe-method
  columns (`AB_ICMPv4`, `AB_TCPv4`, `AB_DNSv4`, `GCD_ICMPv4`, `GCD_TCPv4`) rather than the single
  aggregate confidence field the docs describe, so the assignment combines them with `greatest()`.
  Anything written against the documented schema will not run against the actual file.
- `IPv4-latest` means results change under you between runs. There is no pinned snapshot URL, so a
  number computed today is not exactly reproducible tomorrow — worth reporting the run date alongside
  any figure derived from it.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| DNS | `https://manycast.net/api/v1/export/IPv4-latest.parquet` | `nids-dns-ecosystem-key/00-environment-check.ipynb:153`, `nids-dns-ecosystem-key.ipynb:1047` |

## Validate

HTTP HEAD. The file is large enough that a reachability check should not download it.

## See also

- `nids-dns-ecosystem/Datasets.md` — the confidence filters and the documented schema table
- `nids-dns-ecosystem-key/openintel_csv/openintel_data_dictionary.md` — `## Anycast Census columns`,
  generated from the live file
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the
  `manycast.net` egress row
