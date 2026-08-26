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
public = true                       # reachable without credentials
served_from = "both"                # both | ceph-only | not-nrp | in-namespace
setup = "none"                      # none | documented | undocumented
time_sensitive = "yes"              # yes | no | low | live
credentials = []                    # env var names, in the order the checker reads them

[access]
transport = "osdf"          # osdf | https | ceph | s3 | s3a | postgres | bolt
base = "..."                # or `host` for ceph -- prepended by Dataset.url()
template = "/routeviews/{collector}/bgpdata/{period}/RIBS"
pins = ["collector", "period"]      # every placeholder above, and nothing else

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
```

### Check kinds

| kind | Does | Extra keys |
|---|---|---|
| `http-head` | HEAD, expects 2xx | `url` (overrides the template), `note_suffix` |
| `parquet-magic` | Range-GET 4 bytes, expects `PAR1` | |
| `magic` | Range-GET, expects leading bytes | `magic` (hex) |
| `readable` | Range-GET 8 bytes, no assertion | |
| `osdf-listing` | `OSDFFileSystem().ls()`, expects non-empty | |
| `bolt` | Neo4j `verify_connectivity()` | |
| `s3-list` | `list_objects_v2` under the resolved prefix | `skip_hint` |
| `sql-tables` | lists tables in `access.schema_name` | `skip_hint` |

`magic` is hex-encoded (`425a68`, not `BZh`) so the TOML stays plain text.

Adding a kind means adding a branch to `run_check()` in
[scripts/check-datasets.py](../scripts/check-datasets.py). Adding a *dataset* that uses an
existing kind means adding one TOML file and nothing else.

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

## Keeping the marking

`DESIGN.md`'s **[verified]** / **[unverified]** convention applies inside these files too,
as TOML comments. A pin read out of a notebook is verified; one inferred from a
requirements file is not. Do not quietly promote one to the other.

Per the rule in the top-level `CLAUDE.md`: a dataset marked `setup = "undocumented"` has
no recoverable provisioning procedure, and its README's `## Setup` section **must not** be
filled in with a guess. The TOML records the same fact in a field a script can act on.
