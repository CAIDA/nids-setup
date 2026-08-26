# NIDS on NRP — design notes

The standing brief behind this repo: what is being built, why it is built that way, what it
currently covers, and what is still unresolved.

> **Keep this compacted.** This is not a changelog. When something here stops being load-bearing,
> delete it rather than appending. Every claim is marked **[verified]** (confirmed against NRP docs,
> an assignment repo, or a real run) or **[unverified]** (a recommendation or inference awaiting
> confirmation). Preserve that distinction — it is the difference between fact and intent.

## What is being built

One JupyterHub, in one NRP namespace, serving every NIDS assignment as its own **spawner profile**,
all sharing **one combined container image**. The image is built with Docker by a maintainer and
pushed to a public container registry; readers of the setup guides only pull it.

**You do not need a hub per assignment.** **[verified]** A JupyterHub deployment is bound to one
namespace, one hostname, one CILogon OAuth application, one culling policy, and one admin set. The
assignments differ only in their Python environment and memory footprint — both per-profile (and
per-image) settings *inside* a single hub. Three hubs would triple the CILogon registrations,
callback URLs, namespaces, and culling configs for no benefit.

**Deploying your own hub is optional.** **[verified]** Students can instead use the hosted NRP
service at [jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io), logging in
via CILogon and picking an instance size per assignment — which is what the assignment READMEs
themselves instruct. Deploy your own when you want pinned per-assignment images, shared dataset
volumes, roster-based access control, and a stable spawner menu, i.e. a managed course environment.
The hosted service culls a container ~1 hour after the browser disconnects and starts the home
directory at 5 GB (extendable on request).

## Setup chain

Because deploying a hub is optional, the chain is **two paths, not one** — the reader picks in
[README.md](README.md) before doc 1, and each guide declares which path it serves. Most of the chain
turns out to be own-hub-only: on the community hub the reader needs a namespace and the
verification notebook, nothing else. `kubectl` is deployment tooling only — **[verified]** no
assignment touches Kubernetes; every dataset is read from inside the server over HTTP, S3A, or
Postgres.

| Guide | Establishes | Path |
|---|---|---|
| [docs/1_kubectl_install.md](docs/1_kubectl_install.md) | `kubectl` + the `kubelogin` OIDC plugin | Own hub |
| [docs/2_nrp_namespace.md](docs/2_nrp_namespace.md) | Steps 1–3: NRP Portal access and a namespace · Steps 4–5: `HUB_HOST` and the CILogon OAuth app | Both · Own hub |
| [docs/3_kubectl_config.md](docs/3_kubectl_config.md) | `kubectl` pointed at the namespace | Own hub |
| [docs/4_nrp_jupyterhub.md](docs/4_nrp_jupyterhub.md) | The Helm deployment, profiles, policy, storage, egress | Own hub |
| [docs/5_verify_hub.md](docs/5_verify_hub.md) | Proof the hub works, from inside a spawned server | Both (community hub: Steps 1–3 only) |

Outside that chain: [docs/0_build_images.md](docs/0_build_images.md) builds and publishes the image.
It is maintainer-only — the reader path starts at doc 1 and the image is already published.

## The environment checks

`kubectl` can prove a pod is `Running` and nothing beyond it. Everything that actually breaks a
class — a dependency missing from the image, a memory limit that didn't apply, egress that reaches
PyPI but not `ftp.ripe.net` — is only visible from inside a spawned server. So the verification
layer is notebooks, not commands:

- [notebooks/test.ipynb](notebooks/test.ipynb) — the hub: kernel, `%pip`, home PVC, memory envelope,
  external egress, in-cluster Ceph, and (as warnings, since the hosted NRP hub has no Spark) the
  image's Spark capability. Run once per spawner profile.
- `00-environment-check.ipynb` in each **answer-key** repo — that assignment's own datasets, via a
  small real read (a listing, a Parquet schema, the first bytes of an object), not a ping.
- [notebooks/check-datasets.ipynb](notebooks/check-datasets.ipynb) — every dataset at once, as a
  reachability pass rather than a deep read. It exists because the per-assignment checks are each
  scoped to one assignment, so no single run answers "is all the data reachable from here".
  [scripts/check-datasets.py](scripts/check-datasets.py) is its laptop-side counterpart, where the
  six Ceph datasets are reported as skipped rather than failed.

Two decisions worth not relitigating:

- **They live in the `-key` repos, not the student repos.** **[verified]** These are instructor
  tools — the question they answer is "is this assignment ready to hand out". ITDK's check reads
  `db_credentials.env`, which students never have.
- **The check runner is duplicated into every notebook rather than imported.** **[verified]** Each
  notebook is handed around as a single file into a fresh server; no import path is safe to assume.
  The duplication is the price of that, and it is the cheaper side of the trade.

[datasets/](datasets/README.md) carries the per-dataset detail — provenance, provisioning, access
paths, and reachability checks, one directory per dataset because most are shared between
assignments. Doc 4 carries the rest of the operational detail (the egress table, cluster policy,
shared storage). This file does not duplicate either — it records the *decisions* and what is open.

## The image

- **Base:** `quay.io/jupyter/all-spark-notebook`, pinned by **OCI image index digest** — see
  [image/Dockerfile](image/Dockerfile). A Spark-capable Jupyter base means the JVM and Spark are
  preinstalled for the DNS assignment; the other profiles ignore the Spark bits. **[unverified]**
  (recommendation — confirm the base's Python stays compatible with the pinned packages).
  Pinning by digest is deliberate: a moving `:latest` invalidates the entire layer cache. The
  *index* digest is pinned, not a platform-specific one, so it still resolves per-architecture.
- **Python dependencies:** [image/requirements.txt](image/requirements.txt), the union of the
  assignments' imports, grouped by which assignment each came from.
- **Pre-staged Spark S3A JARs:** `org.apache.hadoop:hadoop-aws:3.4.0` and
  `software.amazon.awssdk:bundle:2.24.6` are baked into `$SPARK_HOME/jars`. **[verified]** The DNS
  notebook otherwise pulls them from Maven Central via `spark.jars.packages` at session start; the
  pre-stage removes that runtime egress dependency.
- **System requirement:** a JVM, satisfied by the base image. **[verified]**
- **Built size: ~7.0 GB.** **[verified]** Every spawned pod pulls this, so it is the metric to watch
  against the "split off DNS/Spark" trigger below. The redundant pip `pyspark` is part of it.
- **Registry path:** a `nids-hub` repository under a CAIDA-owned registry account, published as
  `:latest` and `:<git-short-sha>`. This is `singleuser.image.name` in
  [configs/values.yaml](configs/values.yaml), currently the `<IMAGE_PATH>` placeholder.
  **[unverified]** The account is not yet chosen; a public Docker Hub repo (`caida/nids-hub`) is the
  recommendation, with GHCR (`ghcr.io/caida/nids-hub`) the alternative. Public matters: a private
  repository forces an `imagePullSecrets` on every namespace that deploys the hub.

## The build path

A maintainer builds `image/` locally with `docker buildx build --platform linux/amd64` and pushes
both tags — wrapped by [scripts/build-push.sh](scripts/build-push.sh) so the flags and the SHA tag
aren't retyped. Nothing in CI builds it, and the readers of docs 1-4 never build it at all. Full
walkthrough in [docs/0_build_images.md](docs/0_build_images.md).

## Decisions and why

| Decision | Choice | Why |
|---|---|---|
| Hub count | One hub, one profile per assignment | **[verified]** A hub binds one namespace/hostname/OAuth app/cull policy; assignments differ only per-profile. |
| Image strategy | One combined image | **[unverified]** (recommendation) The dependency sets are additive, not conflicting; BGP and telescope already share the same prefix-to-AS / MRT stack. Split off **only** if the image becomes unwieldy or a real version-pin conflict appears — and then peel off just DNS/Spark, keeping BGP+telescope together. |
| Spark mode | Local mode, single pod | **[verified]** The DNS notebook sets `conf.setMaster("local[*]")`. No standalone or operator-managed Spark cluster is needed. |
| Builder | `docker buildx` on a maintainer's machine, not CI | **[unverified]** (recommendation) The image changes a handful of times a year, so a hand-run build beats maintaining a pipeline. The rejected alternative was NRP GitLab CI, which only builds repos it hosts — with the sources on GitHub that cost a second git remote pushed on every image change, plus an account, group, and project in the setup path. |
| Registry path | A public `nids-hub` repository, registry-agnostic | **[unverified]** Keeping the registry a variable (`IMAGE=`) means the account can change without touching the Dockerfile or the script; public keeps `imagePullSecrets` out of every deployment. |
| Base image pinning | Digest, not `:latest` | A moving tag invalidates the whole layer cache, turning one-line changes into cold multi-GB rebuilds. |
| Architecture | amd64, explicitly | **[verified]** NRP has both amd64 and arm64 nodes; a single-arch image on the wrong node fails with `exec format error`. `--platform linux/amd64` is therefore mandatory, and on an Apple Silicon build host it means QEMU emulation and a slow build. |

## Assignment coverage

`nids-module-creator/` holds ten assignment directories. The image and
[configs/values.yaml](configs/values.yaml) currently target three, with IYP's Python dependencies
now added but its database not yet deployed.

| Assignment | Profile | Image deps | Notes |
|---|---|---|---|
| `nids-bgp-control-plane` | ✅ | ✅ **[verified]** | Its notebook has since landed: `%pip install pybgpkit-parser pelicanfs pytricia pandas` plus `matplotlib`, all already in `requirements.txt`. The earlier inference from `Datasets.md` was right. |
| `nids-telescope-traffic` | ✅ | ✅ **[verified]** | Pins its own `requirements.txt`. Highest memory profile. |
| `nids-dns-ecosystem` | ✅ | ✅ **[verified]** | Only assignment using Spark. |
| `nids-iyp` | ❌ not yet | ✅ `neo4j`, `python-dotenv` added | **Blocked on a Neo4j instance** — see below. `nids-iyp.ipynb` does not exist yet, so deps come from its `requirements.txt`/`pyproject.toml`, not real imports. |
| `nids-asn-introduction` | ❌ | ✅ nothing to add | **[verified]** Its notebook imports the standard library only and has no `%pip` line; it reads the same two Ceph objects as BGP. Prerequisite of the BGP assignment — adding it is just another profile entry. |
| `nids-irr-rpki-whois` | ❌ | ⚠️ **missing** `py-radix`, `tqdm` | **[verified]** from the notebook's imports. Also the only assignment reading `ftp.ripe.net`, now in doc 4's egress table. |
| `nids-itdk` | ❌ | ⚠️ **missing** `sqlalchemy`, `psycopg2-binary`, `pycountry`, `scipy`, `python-dotenv` | **[verified]** from the notebook's imports. **Blocked on a Postgres instance** — see below, same shape as IYP's Neo4j gap. |
| `nids-geolocation`, `nids-ip-data-plane`, `nids-ucsdnt-expanse` | ❌ | — | Not yet assessed. |

The two ⚠️ rows are recorded, not fixed: adding them to `image/requirements.txt` widens the image
for assignments that have no profile yet, which is a scope decision, not a bug. Each assignment's
`00-environment-check.ipynb` carries its own `%pip` line, so the checks pass today regardless.

### Memory envelopes

| Profile | Guarantee / Limit | Status |
|---|---|---|
| BGP | 4Gi / 8Gi | **[unverified]** inference — RIB parsing is streaming, modest footprint |
| Telescope | 16Gi / 24Gi | **[verified]** the assignment README requires ≥16 GB, recommends 24 |
| DNS | 8Gi / 12Gi | **[unverified]** inference — `Spark.md` sets driver 4G + executor 4G in local mode; sized above their sum with headroom |

### Per-assignment gotchas worth not rediscovering

- **DNS / S3A:** `fs.s3a.vectored.io.enabled=false` and `parquet.hadoop.vectored.io.enabled=false`
  must both stay `false`. **[verified]** Enabling them against this object store causes read
  failures. Do not "optimize" these.
- **`pybgpkit-parser`:** the PyPI package is `pybgpkit-parser`; import it as
  `import pybgpkit_parser as bgpkit`, **not** `import bgpkit`. **[verified]** Prebuilt wheels — no
  `libbgpstream` compile needed.
- **`dnspython`:** imported as `import dns.resolver`. **[verified]**
- **GeoLite2:** the `GeoLite2-City.mmdb` comes from **in-cluster Ceph**, so **the reader** needs no
  MaxMind account or license. **[verified]** That is a statement about the assignment, not about the
  mirror — see the licence question below.

## Infrastructure beyond the hub

Every dataset is inventoried in [datasets/](datasets/README.md), with its own directory recording
provenance, provisioning, access path, and how to check it. Which *hosts* the namespace must reach is
tabulated in [docs/4_nrp_jupyterhub.md](docs/4_nrp_jupyterhub.md#data-access-and-egress) — including
`ftp.ripe.net`, which `nids-irr-rpki-whois` alone touches. **[verified]** Shared datasets go to a
`ReadOnlyMany`/`ReadWriteMany` PVC mounted read-only at `/home/shared`. **[verified]**

### The Ceph-hosted datasets have no documented provisioning

Six datasets are served from the in-cluster Ceph gateway: the customer cone, `as2org`, the IRR WHOIS
dumps, `routeviews-prefix2as`, the UCSD-NT PCAP samples, and GeoLite2. The objects exist and the
assignments read them, but **nothing in any NIDS repository records how they got there** —
**[verified]** by search: no upload script, no bucket policy, no S3 credential for that bucket. Four
of the six encode a date that will eventually need refreshing, and two are not verbatim mirrors:
`as2org.jsonl` is a NIDS-specific flattened rendering, and the PCAP samples are anonymized
derivatives of AUA/DUA-governed telescope data whose anonymization parameters are unrecorded.

Each affected directory under `datasets/` records what is known and what must be recovered, rather
than a guessed procedure.

Two questions follow from the mirror rather than from any one dataset. **[unverified]** Whether
CAIDA's re-serving of GeoLite2 is permitted by MaxMind's licence — the assignment needs no MaxMind
account precisely *because* of the mirror, so the licence question moved rather than disappeared.
And whether serving anonymized telescope derivatives openly is covered by the telescope's AUA/DUA.

### ITDK needs a Postgres instance

`nids-itdk` queries a `caida_itdk` schema in a Postgres deployed into the class namespace from the
assignment's own `postgres.yaml`, with credentials handed out through a `db_credentials.env`
uploaded next to the notebook (`ITDK_READ_DSN`, read-only user). **[verified]** Same shape as the
IYP gap below: nothing in this repo provisions it, and an ITDK profile without it spawns a notebook
that cannot connect. Unlike IYP's Neo4j, Postgres *does* have real role-based access control, so the
read-only credential is genuinely read-only.

### IYP needs a Neo4j instance — not yet built

The IYP assignment queries a self-hosted **Neo4j** loaded from a pinned IYP dump, running in a CAIDA
NRP namespace. **[verified]** The notebook connects over `bolt://` using `IYP_READ_URI`,
`IYP_READ_USER`, `IYP_READ_PASSWORD` read from a `neo4j_credentials.env` placed beside it. Two
access modes are documented: an in-cluster service address when the hub shares the instance's
namespace, or a `kubectl port-forward` tunnel to `bolt://localhost:7687`.

None of this exists in this repo — no Neo4j manifest in `configs/`, no entry in doc 5's egress
table, no credential-distribution story. An IYP profile without it would spawn a notebook that
cannot connect.

> ⚠️ **Neo4j Community Edition has no role-based access control.** **[verified]** There is no
> database-enforced way to issue a read-only credential, and the notebook's `run_query()` keyword
> filter is explicitly "a courtesy check, not a security boundary." A hosted hub hands that
> shared-trust credential to every enrolled student, any one of whom could `DETACH DELETE` the
> graph. Weigh restore-from-pinned-dump on a schedule, a read-only replica, or a Bolt-level proxy
> before going live.

## Mandatory cluster policy

**Non-negotiable — a deployment missing these can get the namespace locked.** **[verified]**

- **Culling.** Not optional. A root-level `cull` block with `timeout` ≤ 21600 (6 hours). The
  template uses `timeout: 3600`, `every: 600`, `concurrency: 10`, `maxAge: 0`. Verify with
  `kubectl logs -n <namespace> deployment/jupyterhub -c hub | grep cull`.
- **Auth lockdown.** Do not leave the hub open. Restrict via `allowed_idps` (your institution's IdP
  EntityID from [cilogon.org/idplist](https://cilogon.org/idplist)) with matching
  `allowed_domains`, and/or an `allowed_users` roster.
- **Admins.** Add the NRP admin users to the admin role for support and debugging. If you use an IdP
  allowlist, **include UCSD** so NRP admins and CAIDA content owners can authenticate.

## Operational good practice

- NRP backs up nightly **except container images** — prune old registry tags so the per-build SHA
  tags don't accumulate. Keep `:latest` and the most recent few.

## The registries

Dataset coordinates used to exist in three places at once: prose in `datasets/<id>/README.md`,
hardcoded constants in `scripts/check-datasets.py`, and again in each assignment's own
`00-environment-check.ipynb`. They now exist once, in `datasets/<id>/dataset.toml`, with
`assignments/registry.toml` supplying the per-assignment pins. `datasets/SCHEMA.md` documents both.

- **Central, not per-assignment.** **[verified]** The per-repo copies had already diverged — the
  RouteViews RIB month is `2026.05` in BGP and `2026.06` in TELESCOPE. Keeping the path shape in one
  place and letting an assignment pin only `period` turns that from two unrelated strings in two
  repos into two values on one dataset, visible in one command
  (`check-datasets.py --list --assignment BGP`). An assignment repo may still override its own block
  with a root `nids.toml`, so adopting this needs no change to any assignment repo.
- **The checker was refactored, not rewritten.** **[verified]** `scripts/check-datasets.py` now
  resolves every coordinate from the registry and holds no paths of its own; its output is
  byte-identical to the pre-refactor version, which is what proves the TOML captured the prose
  faithfully. Its check-runner block stays duplicated verbatim from `notebooks/test.ipynb` as before.
- **The notebooks still may not import it.** `notebooks/check-datasets.ipynb` cannot read
  `nids_registry.py` — the single-file rule in `CLAUDE.md` is not negotiable, since each notebook is
  handed into a fresh server on its own. Keeping it in sync with the registry means *generating* its
  coordinate cell, not importing. **[unverified]** — not built yet; the notebook is unchanged and its
  values are still hand-maintained.
- **Cloning requires a token.** **[verified]** An unauthenticated listing of the CAIDA org returns 36
  `nids*` repos, of which 27 are GitHub Classroom student forks; `nids-setup` itself, every `-key`
  repo, and `nids-module-creator` are private and absent. `scripts/clone-nids-repos.sh` therefore
  refuses to run without one rather than clone a plausible-looking wrong subset, and excludes student
  forks by default.

## Open questions

| Priority | Question |
|---|---|
| High | **The image builds, but has never been pushed or pulled.** **[verified]** `docker buildx build --platform linux/amd64` succeeds and the import set (`pyspark, dpkt, pytricia, pybgpkit_parser, pelicanfs, neo4j`) loads; the base index digest correctly selects amd64 on an arm64 host. Untested: the push, the cluster pull, and a real Spark session. Failure modes are tabulated in [docs/0_build_images.md](docs/0_build_images.md#if-the-build-fails). |
| High | Deploy the IYP Neo4j instance and settle the credential model, including the Community Edition RBAC gap above. The pod manifest survives and is reconstructed in [datasets/iyp-neo4j](datasets/iyp-neo4j/); the dump source and the `iyp-storage` PVC definition do not. |
| High | **Recover how the six Ceph-hosted datasets are provisioned.** **[verified]** as undocumented. Until then the hub's data cannot be rebuilt from scratch by anyone but whoever originally staged it, and the four dated objects cannot be refreshed. Per-dataset gaps are recorded under [datasets/](datasets/README.md). |
| Medium | **Is CAIDA's Ceph mirror licensed to re-serve MaxMind GeoLite2?** **[unverified]** The assignment needs no MaxMind account because of the mirror, which relocates the licence question rather than answering it. Same shape for the anonymized telescope PCAPs under the UCSD-NT AUA/DUA. |
| Medium | `pyspark` in `requirements.txt` is **provably redundant, and inert only by luck.** **[verified]** in the built image: pip does install a second copy at `/opt/conda/.../site-packages/pyspark` (4.2.0), but `sys.path` puts `$SPARK_HOME/python` first — set by the base's `before-notebook.d/10spark-config.sh` hook — so the base's own pyspark 4.2.0 is what imports, matching `spark-core_2.13-4.2.0`. No skew *today* because PyPI's version happens to equal the base's. Bumping either breaks that, and any path skipping the hook picks up the site-packages copy. Drop it from `requirements.txt` (saves build time and image size) once a real Spark session against the DNS notebook confirms nothing depends on it. |
| Medium | Verify NRP egress permits OSDF/`pelicanfs` fetches and S3A reads from `object.openintel.nl` from inside the deployed namespace. [notebooks/check-datasets.ipynb](notebooks/check-datasets.ipynb) answers this for every dataset at once; [scripts/check-datasets.py](scripts/check-datasets.py) already confirms the external half from outside NRP. **[verified]** externally — OSDF listing, `ftp.ripe.net`, `object.openintel.nl`, `manycast.net`, and IYP bolt all reachable from a laptop. |
| Medium | **The pre-staged Spark jars may not remove the Maven dependency they were added for.** **[unverified]** `nids-dns-ecosystem-key.ipynb` still sets `spark.jars.packages`, and Ivy resolution is independent of `$SPARK_HOME/jars` — so a first Spark start in a fresh home directory likely still reaches Maven Central despite the pre-stage. If a run confirms it, either drop `spark.jars.packages` from the notebook or drop the two `curl` fetches from the Dockerfile; keeping both buys nothing. |
| Medium | The image is single-architecture (amd64). Decide between pinning `nodeSelector` to `amd64` and publishing a real multiarch manifest — with `buildx` the latter is just `--platform linux/amd64,linux/arm64`, at the cost of a much slower build. |
| Low | Right-size the BGP and DNS memory envelopes against real runs; only telescope's 16/24 Gi is authoritative. |
| Low | Assess the remaining assignments for profile and dependency needs. **[verified]** `nids-ucsdnt-expanse` needs no NRP profile at all — it runs on SDSC Expanse via Slurm (see [datasets/ucsdnt-expanse-flowtuple](datasets/ucsdnt-expanse-flowtuple/)). `nids-geolocation` has an outline but no code, and will need MaxMind GeoLite2 **CSVs**, a different artifact from the `.mmdb` telescope reads. `nids-ip-data-plane` is an empty stub. |
| Low | Two assignments have no `00-environment-check.ipynb`: `nids-iyp` and `nids-ucsdnt-expanse`. **[verified]** For IYP that is a real gap, since it targets JupyterHub like the six that do have one; for UCSDNT it is expected, since the notebook would have to run under Slurm. |
