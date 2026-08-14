# Datasets

Every dataset the NIDS assignments read, in one place: who produced it, whether the public version
can be used or a NIDS administrator has to build a NIDS-specific version first, how it is reached,
and how to check that it is still reachable.

This directory is deliberately **cross-assignment**. Each assignment's own `Datasets.md` explains
what its data *means* and why that source was chosen; each answer-key repo's
`00-environment-check.ipynb` hard-codes the values *that assignment* uses. Neither can answer "what
is the full set of data this hub needs, and what would it take to stand it up from scratch" — several
datasets are shared, and the per-assignment copies are free to drift. They already have: the
RouteViews RIB month is `2026.05` in BGP and `2026.06` in TELESCOPE.

Three files own three different things, and none of them duplicates the others:

| File | Owns |
|---|---|
| `datasets/` (here) | Provenance, provisioning, access paths, and reachability checks. |
| Each assignment's `Datasets.md` | What the data means, schemas, and why this source. |
| [docs/4_nrp_jupyterhub.md](../docs/4_nrp_jupyterhub.md#data-access-and-egress) | Which hosts the hub's namespace must be able to reach. |

## Assignments

Codes are the ones published in
[assignments.json](https://www.caida.org/projects/nids/assignments/assignments.json), behind the
[NIDS assignments page](https://www.caida.org/projects/nids/assignments/).

| code | name |
|---|---|
| ASN | ASN Introduction |
| BGP | BGP Control Plane |
| IRR | Registries: WHOIS, IRR & RPKI |
| ITDK | ITDK |
| DNS | DNS Ecosystem |
| TELESCOPE | Network Telescope Traffic |
| IYP | Internet Yellow Pages |
| UCSDNT | UCSD Network Telescope (Expanse) |

`IYP` and `UCSDNT` are not yet listed on the assignments page; the codes are settled and will appear
there. Note also that the published `IRR` entry links to `nids-irr-rpki-whois-local`, while the
dataset paths below come from `nids-irr-rpki-whois` — the two repos are variants of the same
assignment, not a mistake in this table.

## Inventory

| dataset | assignments | produced by | setup | public | served from | time-sensitive |
|---|---|---|---|---|---|---|
| [routeviews-bgp-rib](routeviews-bgp-rib/) | BGP, TELESCOPE | External — RouteViews (U. Oregon) | | Yes | Both — OSDF | Yes — dated month directory |
| [caida-as-customer-cone](caida-as-customer-cone/) | ASN, BGP | CAIDA | ❌ | Yes | Ceph only | Yes — dated serial filename |
| [caida-as2org](caida-as2org/) | ASN, BGP | CAIDA | ❌ | Yes | Ceph only | No — stable filename |
| [caida-irr-whois-dumps](caida-irr-whois-dumps/) | IRR | CAIDA — collected from 16 external IRRs | ❌ | Yes | Ceph only | Yes — dated directory |
| [routeviews-prefix2as](routeviews-prefix2as/) | IRR | CAIDA — derived from RouteViews | ❌ | Yes | Ceph only | Yes — dated path |
| [ripe-rpki-roas](ripe-rpki-roas/) | IRR | External — RIPE NCC | | Yes | Both — `ftp.ripe.net` | Yes — dated path per trust anchor |
| [openintel-fdns](openintel-fdns/) | DNS | External — OpenINTEL | | Yes | Both — S3A | Yes — year/month/day partitions |
| [anycast-census](anycast-census/) | DNS | External — LACeS / manycast.net | | Yes | Both — HTTPS | Low — `IPv4-latest`, no date |
| [ucsd-nt-pcap-samples](ucsd-nt-pcap-samples/) | TELESCOPE | CAIDA — UCSD Network Telescope | ❌ | Yes | Ceph only | Yes — dated sample filenames |
| [maxmind-geolite2](maxmind-geolite2/) | TELESCOPE | External — MaxMind, CAIDA-mirrored | ❌ | Yes, via the mirror | Ceph only | Yes — dated filename |
| [itdk-postgres](itdk-postgres/) | ITDK | CAIDA | ✅ | **No** — `ITDK_READ_DSN` | In-namespace Postgres | Yes — dated release |
| [iyp-neo4j](iyp-neo4j/) | IYP | External — IIJ Lab / IHR | ✅ | Yes (public instance) | Both | Live — continuously updated |
| [ucsdnt-expanse-flowtuple](ucsdnt-expanse-flowtuple/) | UCSDNT | CAIDA — UCSD Network Telescope | ✅ | **No** — `UCSD_NT_S3_*` | **Not NRP** — SDSC Expanse | Yes — y/m/d partitions |

**Legend.**
**produced by** — who made the data. CAIDA or an external organisation. Independent of where it is
served from: `maxmind-geolite2` is external-produced but CAIDA-mirrored, and `routeviews-prefix2as`
is CAIDA-produced from external input.
**setup** — whether a NIDS administrator must build a NIDS-specific version before the assignment
works. ✅ = required, and this directory documents how. ❌ = required, but the procedure is **not
written down anywhere**; the directory records what is known and what must be recovered. Blank = the
public version is used directly, nothing to set up.
**public** — reachable without credentials.
**served from** — `Ceph only` = the in-cluster object store at `rook-ceph-rgw-nautiluss3.rook`,
which does not resolve outside NRP. `Both` = reachable from NRP and from a laptop. `Not NRP` = not
NRP infrastructure at all.
**time-sensitive** — the access path encodes a specific date or period that will need updating.

### Six of thirteen datasets have no documented provisioning

Every dataset served from in-cluster Ceph is marked ❌. The objects exist and the assignments read
them, but nothing in any repo records who put them there, from which upstream source, on what
cadence, or with which credentials — and four of the six encode a date that will eventually need
refreshing. That is the largest gap this directory exposes, and it is tracked in
[DESIGN.md](../DESIGN.md#open-questions). The affected datasets are
[caida-as-customer-cone](caida-as-customer-cone/), [caida-as2org](caida-as2org/),
[caida-irr-whois-dumps](caida-irr-whois-dumps/), [routeviews-prefix2as](routeviews-prefix2as/),
[ucsd-nt-pcap-samples](ucsd-nt-pcap-samples/), and [maxmind-geolite2](maxmind-geolite2/).

Two consequences of the mirror worth stating outright:

- **Redistribution.** The mirror re-serves externally-produced data. GeoLite2 is the pointed case:
  MaxMind normally gates it behind an account and a licence, and the mirror is precisely why the
  assignment needs neither. Whether the mirror is licensed to re-serve it is an open question, not a
  detail. **[unverified]**
- **Governance.** UCSD Network Telescope data is CAIDA's own but AUA/DUA-governed, and the raw
  captures stay on SDSC Expanse. The two telescope datasets here are not equivalent:
  [ucsd-nt-pcap-samples](ucsd-nt-pcap-samples/) is an anonymized derivative served openly from Ceph,
  while [ucsdnt-expanse-flowtuple](ucsdnt-expanse-flowtuple/) is the credentialed FlowTuple archive
  and never leaves Expanse.

## Shared prerequisites

Reachability requirements that are not datasets, and so are not listed above:

- **PyPI egress.** Every assignment except ASN and IYP opens with a `%pip install`. Checked by
  [notebooks/test.ipynb](../notebooks/test.ipynb).
- **Public DNS resolution.** DNS resolves real name servers at runtime with `dns.resolver` — a
  *required* check in its own environment check, distinct from reading the OpenINTEL archive.
- **Spark JAR resolution.** DNS and UCSDNT both set `spark.jars.packages`, which resolves through
  Ivy from Maven Central on first use. The `nids-hub` image pre-stages the two JARs DNS needs so
  this is not a hard dependency there; on the hosted NRP hub it is.
- **A writable working directory.** Several assignments cache downloads locally: ASN and BGP write
  into `data/`, IRR into `cache_nids/`, TELESCOPE writes `prefix_to_asn.pkl` and per-capture
  `.parquet` files.

## Checking access

Two checkers, deliberately split by where they can run:

| | Runs | Covers |
|---|---|---|
| [scripts/check-datasets.py](../scripts/check-datasets.py) | A laptop, outside NRP | Everything reachable from outside. The six Ceph datasets are reported as skipped, not failed. |
| [notebooks/check-datasets.ipynb](../notebooks/check-datasets.ipynb) | Inside a spawned server on the hub | Everything, including Ceph. |

Both are **reachability** passes — a HEAD, a range-GET of the first bytes, a directory listing, a
bolt handshake. Neither replaces an assignment's own `00-environment-check.ipynb`, which does real
reads (a Parquet schema, a Spark session, a Postgres query) and is the authoritative check that one
assignment is ready to hand out.

## Out of scope

- **ASN** has no directory of its own — it reads
  [caida-as-customer-cone](caida-as-customer-cone/) and [caida-as2org](caida-as2org/), and appears
  in their `Used by`.
- **`nids-geolocation`** has no dataset paths yet. Its outline calls for RIR delegation files, Hoiho,
  an IXP dataset, and MaxMind GeoLite2 **CSVs** — a different artifact from the `.mmdb` TELESCOPE
  uses, so it will need its own directory rather than an entry here.
- **`nids-ip-data-plane`** is an empty stub; **`nids-telescope-iraq-2026`** is a slide deck. Neither
  has datasets.
