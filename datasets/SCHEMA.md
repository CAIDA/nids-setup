# Registry schema

Two TOML registries hold every coordinate the NIDS tooling needs. They are the
machine-readable half of what `datasets/*/README.md` and `DESIGN.md` describe in prose;
neither replaces the other.

| File | One per | Owns |
|---|---|---|
| `datasets/<id>/dataset.toml` | dataset | transport, path template, placeholders, how to check it |
| `assignments/registry.toml` | assignment | repos, environment, and the pins it supplies per dataset |

Read them with [scripts/nids_registry.py](../scripts/nids_registry.py). Validate them with
`scripts/nids_registry.py --validate`, which is the closest thing this repo has to a test
suite — it proves every assignment reference resolves and no placeholder is left dangling.

## Why the coordinates are central

The per-assignment copies drift. The RouteViews RIB month is `2026.05` in BGP and
`2026.06` in TELESCOPE — two independent strings in two repos, with nothing to make the
divergence visible. Here the path shape exists once and each assignment pins only
`period`, so the drift shows up in one command:

```
$ scripts/check-datasets.py --list --assignment BGP
BGP          routeviews-bgp-rib   https://osdf-director.osg-htc.org/routeviews/route-views3/bgpdata/2026.05/RIBS
$ scripts/check-datasets.py --list --assignment TELESCOPE
TELESCOPE    routeviews-bgp-rib   https://osdf-director.osg-htc.org/routeviews/route-views3/bgpdata/2026.06/RIBS
```

**An assignment pins placeholders, never URLs.** If you find yourself writing a full path
into `assignments/registry.toml`, the dataset's template is missing a placeholder.

## `datasets/<id>/dataset.toml`

```toml
schema = 1                  # only 1 exists; the loader rejects anything else
id = "routeviews-bgp-rib"   # must equal the directory name
name = "RouteViews BGP RIB (MRT)"
used_by = ["BGP", "TELESCOPE"]      # assignment codes
produced_by = "external"            # external | caida
public = true                       # the UPSTREAM data is openly published
public_access = true                # THIS artifact is downloadable by anyone -- see below
served_from = "both"                # both | ceph-only | not-nrp | in-namespace
setup = "none"                      # none | documented | undocumented
time_sensitive = "yes"              # yes | no | low | live
credentials = []                    # env var names, in the order the checker reads them

[access]
transport = "osdf"          # osdf | https | ceph | s3 | s3a | postgres | bolt
base = "..."                # or `host` for ceph -- prepended by Dataset.url()
template = "/routeviews/{collector}/bgpdata/{period}/RIBS"
pins = ["collector", "period"]      # every placeholder above, and nothing else

[access.public]             # optional: the open-web coordinate, when [access] is internal
transport = "https"         # same fields as [access], plus:
verified = "2026-08-27"     # required -- when it was last confirmed reachable
base = "https://publicdata.caida.org/datasets/as-relationships/serial-1"
template = "{serial}.ppdc-ases.txt.bz2"
pins = ["serial"]

[defaults]                  # what the checkers use with no assignment pin
collector = "route-views3"
period = "2026.05"

[check]
section = "external"        # external | ceph | credentialed -- the checker's three groups
order = 10                  # position within the section
label = "osdf: routeviews rib listing (BGP, TELESCOPE)"
kind = "osdf-listing"       # dispatch; see below
needs_module = "pelicanfs.core"     # optional import gate
needs_hint = "pip install pelicanfs"

[check.public]              # optional: the check for [access.public], same fields
section = "external"        # a public coordinate is external by definition
kind = "http-magic"
magic = "425a68"
```

### `public` vs `public_access`, and `[access.public]`

These are three different facts and conflating the first two is what made an earlier pass
at the release scope wrong.

- **`public`** — is the *upstream* data openly published? True of `caida-as2org`, whose
  upstream is on `publicdata.caida.org`, even while NIDS reads an in-cluster mirror.
- **`public_access`** — can anyone download **the artifact this dataset resolves to**,
  from the open web, with no account, allocation, or vetting? Getting onto NRP or SDSC
  Expanse is a vetting process and does not count. **This is the release-1 test**, and
  `nids_registry.validate()` refuses to let an `r1` module read a dataset where it is
  false. It defaults to `public` when unset, so a new dataset is never silently admitted
  on a field nobody set.
- **`[access.public]`** — the coordinate that makes `public_access` true when `[access]`
  points somewhere not everyone can reach. When present it is what `resolve()`, `url()`,
  `pins`, `transport` and `check` all use; `[access]` remains recorded as the in-cluster
  mirror and is reachable via `resolve_mirror()` / `mirror_url()`.

A `verified` date is required on `[access.public]`. Public endpoints are outside CAIDA's
control and drift; a coordinate nobody has confirmed since some date should say so.

### Check kinds

| kind | Does | Extra keys |
|---|---|---|
| `http-head` | HEAD, expects 2xx | `url` (overrides the template), `note_suffix` |
| `parquet-magic` | Range-GET 4 bytes, expects `PAR1` | |
| `magic` | Range-GET over Ceph, expects leading bytes | `magic` (hex) |
| `http-magic` | Range-GET over HTTP(S), expects leading bytes | `magic` (hex) |
| `readable` | Range-GET 8 bytes, no assertion | |
| `osdf-listing` | `OSDFFileSystem().ls()`, expects non-empty | |
| `bolt` | Neo4j `verify_connectivity()` | |
| `s3-list` | `list_objects_v2` under the resolved prefix | `skip_hint` |
| `sql-tables` | lists tables in `access.schema_name` | `skip_hint` |
| `http-fields` | parses the first JSON-lines record, expects named fields | `fields` (list) |

`magic` is hex-encoded (`425a68`, not `BZh`) so the TOML stays plain text.

**Magic bytes prove format, never content, and the difference has bitten us.** `caida-as2org`
passed `http-magic` for a week while publicdata served a schema no notebook could read — the gzip
magic was correct throughout. A dataset whose records the notebooks parse *by field name* should
use `http-fields` and name those fields, so a schema change fails the check instead of the
assignment.

Adding a kind means adding a branch to `run_check()` in
[scripts/check-datasets.py](../scripts/check-datasets.py). Adding a *dataset* that uses an
existing kind means adding one TOML file and nothing else.

## `[stage]` — how a dataset lands on disk

Optional. A dataset with a `[stage]` block can be pre-placed by `nids-setup.py data` into each
module's own `data/` directory, which is what lets a notebook run without reaching the dataset's
own transport.

```toml
[stage]
filename = "as2org.jsonl"      # what the notebook expects in data/; may contain pins
into = ["ASN", "BGP"]          # which modules get a copy
transform = "as2org-flatten"   # optional; a named function in nids-setup.py
```

Per module rather than a shared cache because the notebooks use relative paths —
`Path("data/as2org.jsonl")` — so a file anywhere else is invisible to them.

`transform` exists because a public coordinate is not always byte-equivalent to the mirror the
notebooks were written against. `as2org-flatten` is the only one: publicdata serves CAIDA's raw
`Organization` / `ASN` two-record export, and the notebooks parse the flattened
one-row-per-organisation form the Ceph mirror holds, so staging rebuilds it. The rule this encodes
is worth keeping — **when a public source differs from the mirror, the tooling absorbs the
difference so the assignment text does not have to change.**

Transforms run only for `--local`. On `--nrp` the mirror already holds the expected form.

## `assignments/registry.toml`

One block per assignment code, plus `[CODE.environment]` and repeated
`[[CODE.datasets]]`. The one non-obvious part is the environment split:

```toml
[ITDK.environment]
extra = ["sqlalchemy", "psycopg2-binary"]

[ITDK.environment.key]      # merged over the above for the answer-key repo only
extra = ["..."]             # `extra` appends; every other key replaces
```

That is the README's "the environments required for the assignment and key repos might
differ" case. When a `[CODE.environment.key]` block is absent or empty, the two roles can
share one environment.

`status` is `active` | `blocked` | `offsite` | `stub`. `blocked` carries a `blocked_on`
string; `offsite` means the assignment does not run on the NRP hub at all (UCSDNT runs on
SDSC Expanse under Slurm).

`release` is `r1` | `later`, and it is **editorial** — it records a decision about which
modules ship first, which is not derivable from the dataset fields. It defaults to
`later`: a module opts into the release, and can never land in it by omission. The
release scopes *modules*; the datasets in scope follow from what those modules pin, which
is why `routeviews-prefix2as` is out of v1 despite being publicly downloadable — its only
reader is IRR.

## Keeping the marking

`DESIGN.md`'s **[verified]** / **[unverified]** convention applies inside these files too,
as TOML comments. A pin read out of a notebook is verified; one inferred from a
requirements file is not. Do not quietly promote one to the other.

Per the rule in the top-level `CLAUDE.md`: a dataset marked `setup = "undocumented"` has
no recoverable provisioning procedure, and its README's `## Setup` section **must not** be
filled in with a guess. The TOML records the same fact in a field a script can act on.
