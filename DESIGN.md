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

Two decisions worth not relitigating:

- **They live in the `-key` repos, not the student repos.** **[verified]** These are instructor
  tools — the question they answer is "is this assignment ready to hand out". ITDK's check reads
  `db_credentials.env`, which students never have.
- **The check runner is duplicated into every notebook rather than imported.** **[verified]** Each
  notebook is handed around as a single file into a fresh server; no import path is safe to assume.
  The duplication is the price of that, and it is the cheaper side of the trade.

Doc 4 carries the operational detail (per-assignment data paths, the egress table, cluster policy,
shared storage). This file does not duplicate it — it records the *decisions* and what is open.

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
| `nids-irr-rpki-whois` | ❌ | ⚠️ **missing** `py-radix`, `tqdm` | **[verified]** from the notebook's imports. Also the only assignment reading `ftp.ripe.net` (see the egress note below). |
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
- **GeoLite2:** the `GeoLite2-City.mmdb` comes from **in-cluster Ceph**, so no MaxMind account or
  license is needed. **[verified]** (This supersedes an earlier open question about provisioning it.)

## Infrastructure beyond the hub

Data sources, reachability, and the in-cluster vs external egress split are tabulated in
[docs/4_nrp_jupyterhub.md](docs/4_nrp_jupyterhub.md#data-access-and-egress). Shared datasets go to a
`ReadOnlyMany`/`ReadWriteMany` PVC mounted read-only at `/home/shared`. **[verified]**

That table is missing `ftp.ripe.net`. **[verified]** `nids-irr-rpki-whois` fetches RPKI ROA dumps
from `https://ftp.ripe.net/ripe/rpki/{ta}.tal/…/roas.csv.xz` for five trust anchors — external
egress to a host no other assignment touches. Add it to the table when IRR/RPKI gets a profile.

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

## Open questions

| Priority | Question |
|---|---|
| High | **The image builds, but has never been pushed or pulled.** **[verified]** `docker buildx build --platform linux/amd64` succeeds and the import set (`pyspark, dpkt, pytricia, pybgpkit_parser, pelicanfs, neo4j`) loads; the base index digest correctly selects amd64 on an arm64 host. Untested: the push, the cluster pull, and a real Spark session. Failure modes are tabulated in [docs/0_build_images.md](docs/0_build_images.md#if-the-build-fails). |
| High | Deploy the IYP Neo4j instance and settle the credential model, including the Community Edition RBAC gap above. |
| Medium | `pyspark` in `requirements.txt` is **provably redundant, and inert only by luck.** **[verified]** in the built image: pip does install a second copy at `/opt/conda/.../site-packages/pyspark` (4.2.0), but `sys.path` puts `$SPARK_HOME/python` first — set by the base's `before-notebook.d/10spark-config.sh` hook — so the base's own pyspark 4.2.0 is what imports, matching `spark-core_2.13-4.2.0`. No skew *today* because PyPI's version happens to equal the base's. Bumping either breaks that, and any path skipping the hook picks up the site-packages copy. Drop it from `requirements.txt` (saves build time and image size) once a real Spark session against the DNS notebook confirms nothing depends on it. |
| Medium | Verify NRP egress permits OSDF/`pelicanfs` fetches and S3A reads from `object.openintel.nl` from inside the deployed namespace. The checks in [docs/5_verify_hub.md](docs/5_verify_hub.md) answer this in one run — nothing else does. |
| Medium | **The pre-staged Spark jars may not remove the Maven dependency they were added for.** **[unverified]** `nids-dns-ecosystem-key.ipynb` still sets `spark.jars.packages`, and Ivy resolution is independent of `$SPARK_HOME/jars` — so a first Spark start in a fresh home directory likely still reaches Maven Central despite the pre-stage. If a run confirms it, either drop `spark.jars.packages` from the notebook or drop the two `curl` fetches from the Dockerfile; keeping both buys nothing. |
| Medium | The image is single-architecture (amd64). Decide between pinning `nodeSelector` to `amd64` and publishing a real multiarch manifest — with `buildx` the latter is just `--platform linux/amd64,linux/arm64`, at the cost of a much slower build. |
| Low | Right-size the BGP and DNS memory envelopes against real runs; only telescope's 16/24 Gi is authoritative. |
| Low | Assess the three still-unassessed assignments (`nids-geolocation`, `nids-ip-data-plane`, `nids-ucsdnt-expanse`) for profile and dependency needs. |
