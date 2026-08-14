# RIPE RPKI ROAs (validated payloads)

Daily snapshots of validated RPKI Route Origin Authorizations, published by RIPE NCC per trust
anchor, used to check observed BGP prefix-origin pairs against what the RPKI authorises.

- **Used by:** IRR
- **Produced by:** External — RIPE NCC
- **Served from:** Both — external egress to `ftp.ripe.net`
- **Public version usable:** Yes — read directly
- **Setup:** none needed
- **Credentials:** none
- **Time-sensitive:** Yes — the path encodes `YYYY/MM/DD`, per trust anchor
- **Licence / governance:** open

## Access

Plain HTTPS GET of an xz-compressed CSV, one path per trust anchor per day:

```python
RPKI_TRUST_ANCHORS = ["afrinic", "ripencc", "arin", "lacnic", "apnic"]

url = f"https://ftp.ripe.net/ripe/rpki/{ta}.tal/{yyyy}/{mm}/{dd}/roas.csv.xz"
```

- The RIPE trust anchor is `ripencc`, **not** `ripe`. A path built with `ripe.tal` 404s.
- Five trust anchors, so a full day is five fetches.
- **This is the only assignment that reaches `ftp.ripe.net`.** A namespace whose egress allows CAIDA
  and OSDF but not RIPE will pass every other check and fail only this one, which is exactly why the
  checkers probe it.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| IRR | `https://ftp.ripe.net/ripe/rpki/afrinic.tal/2023/03/01/roas.csv.xz` (reachability probe) | `nids-irr-rpki-whois-key/00-environment-check.ipynb:183` |
| IRR | all five anchors, monthly snapshots Jan–Jun 2023 | `nids-irr-rpki-whois-key/nids-irr-rpki-whois-key.ipynb:121-127,253` |

## Validate

HTTP HEAD against one real ROA URL. This is the check that distinguishes "egress is broken" from
"egress is fine but RIPE specifically is not allowed".

## See also

- `nids-irr-rpki-whois/Datasets.md`
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the
  `ftp.ripe.net` egress row
