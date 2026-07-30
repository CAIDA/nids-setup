# NIDS on NRP — design notes

The standing brief behind this repo: what is being built, why it is built that way, what it
currently covers, and what is still unresolved.

> **Keep this compacted.** This is not a changelog. When something here stops being load-bearing,
> delete it rather than appending. Every claim is marked **[verified]** (confirmed against NRP docs,
> an assignment repo, or a real run) or **[unverified]** (a recommendation or inference awaiting
> confirmation). Preserve that distinction — it is the difference between fact and intent.

## What is being built

One JupyterHub, in one NRP namespace, serving every NIDS assignment as its own **spawner profile**,
all sharing **one combined container image**. The image is built by NRP GitLab CI/CD and published
to NRP GitLab's container registry.

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

| Guide | Establishes |
|---|---|
| [docs/1_kubectl_install.md](docs/1_kubectl_install.md) | `kubectl` + the `kubelogin` OIDC plugin |
| [docs/2_nrp_namespace.md](docs/2_nrp_namespace.md) | NRP Portal access, a namespace, and your `HUB_HOST` |
| [docs/3_kubectl_config.md](docs/3_kubectl_config.md) | `kubectl` pointed at the namespace |
| [docs/4_nrp_gitlab.md](docs/4_nrp_gitlab.md) | GitLab group/project, the CI pipeline, the published image |
| [docs/5_nrp_jupyterhub.md](docs/5_nrp_jupyterhub.md) | The Helm deployment, profiles, policy, storage, egress |

Doc 5 carries the operational detail (per-assignment data paths, the egress table, cluster policy,
shared storage). This file does not duplicate it — it records the *decisions* and what is open.

## The image

- **Base:** `quay.io/jupyter/all-spark-notebook`, pinned by **OCI image index digest** — see
  [image/Dockerfile](image/Dockerfile). A Spark-capable Jupyter base means the JVM and Spark are
  preinstalled for the DNS assignment; the other profiles ignore the Spark bits. **[unverified]**
  (recommendation — confirm the base's Python stays compatible with the pinned packages).
  Pinning by digest is deliberate: a moving `:latest` invalidates the entire CI layer cache. The
  *index* digest is pinned, not a platform-specific one, so it still resolves per-architecture.
- **Python dependencies:** [image/requirements.txt](image/requirements.txt), the union of the
  assignments' imports, grouped by which assignment each came from.
- **Pre-staged Spark S3A JARs:** `org.apache.hadoop:hadoop-aws:3.4.0` and
  `software.amazon.awssdk:bundle:2.24.6` are baked into `$SPARK_HOME/jars`. **[verified]** The DNS
  notebook otherwise pulls them from Maven Central via `spark.jars.packages` at session start; the
  pre-stage removes that runtime egress dependency.
- **System requirement:** a JVM, satisfied by the base image. **[verified]**
- **Registry path:** `gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub`,
  published as `:latest` and `:<short-sha>`. This is `singleuser.image.name` in
  [configs/values.yaml](configs/values.yaml).

## The build path

Sources live on GitHub (`CAIDA/nids-setup`), but NRP GitLab CI only builds repos hosted in NRP
GitLab — so the GitLab project is added as a **second git remote** (`nrp`) and pushed to. Pushing
carries [.gitlab-ci.yml](.gitlab-ci.yml), which builds with **Kaniko** on the ordinary Kubernetes
runners. Full walkthrough in [docs/4_nrp_gitlab.md](docs/4_nrp_gitlab.md).

## Decisions and why

| Decision | Choice | Why |
|---|---|---|
| Hub count | One hub, one profile per assignment | **[verified]** A hub binds one namespace/hostname/OAuth app/cull policy; assignments differ only per-profile. |
| Image strategy | One combined image | **[unverified]** (recommendation) The dependency sets are additive, not conflicting; BGP and telescope already share the same prefix-to-AS / MRT stack. Split off **only** if the image becomes unwieldy or a real version-pin conflict appears — and then peel off just DNS/Spark, keeping BGP+telescope together. |
| Spark mode | Local mode, single pod | **[verified]** The DNS notebook sets `conf.setMaster("local[*]")`. No standalone or operator-managed Spark cluster is needed. |
| Builder | Kaniko, not Docker | **[verified]** NRP has only one dedicated Docker build server; Kaniko runs on the ordinary runners. |
| Registry path | A `/nids-hub` sub-repository under the project | A named sub-repository lets one project publish several images, which matters if the DNS/Spark image is ever split off. |
| Base image pinning | Digest, not `:latest` | A moving tag invalidates the whole Kaniko cache, turning one-line changes into cold multi-GB rebuilds. |
| Architecture | amd64 in practice | **[verified]** NRP has both amd64 and arm64 nodes; a single-arch image on the wrong node fails with `exec format error`. Kaniko builds for its runner's architecture. |

## Assignment coverage

`nids-module-creator/` holds ten assignment directories. The image and
[configs/values.yaml](configs/values.yaml) currently target three, with IYP's Python dependencies
now added but its database not yet deployed.

| Assignment | Profile | Image deps | Notes |
|---|---|---|---|
| `nids-bgp-control-plane` | ✅ | ⚠️ inferred | **[unverified]** The `.ipynb` was not yet committed and there is no `requirements.txt`; deps inferred from `Datasets.md` and the shared telescope stack. Confirm when the notebook lands. |
| `nids-telescope-traffic` | ✅ | ✅ **[verified]** | Pins its own `requirements.txt`. Highest memory profile. |
| `nids-dns-ecosystem` | ✅ | ✅ **[verified]** | Only assignment using Spark. |
| `nids-iyp` | ❌ not yet | ✅ `neo4j`, `python-dotenv` added | **Blocked on a Neo4j instance** — see below. `nids-iyp.ipynb` does not exist yet, so deps come from its `requirements.txt`/`pyproject.toml`, not real imports. |
| `nids-asn-introduction` | ❌ | — | Prerequisite of the BGP assignment. **[verified]** Adding it is just another profile entry. |
| `nids-geolocation`, `nids-ip-data-plane`, `nids-irr-rpki-whois`, `nids-itdk`, `nids-ucsdnt-expanse` | ❌ | — | Not yet assessed. |

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
[docs/5_nrp_jupyterhub.md](docs/5_nrp_jupyterhub.md#data-access-and-egress). Shared datasets go to a
`ReadOnlyMany`/`ReadWriteMany` PVC mounted read-only at `/home/shared`. **[verified]**

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

- Keep `values.yaml` under version control in NRP GitLab; auto-redeploy on change via the
  [k8s GitLab integration](https://nrp.ai/documentation/userdocs/development/k8s-integration/).
  **[verified]**
- NRP backs up nightly **except container images** — enable registry tag cleanup so SHA tags and
  Kaniko cache layers don't accumulate on a shared cluster.

## Open questions

| Priority | Question |
|---|---|
| High | **The CI pipeline has never run end to end.** The first run is effectively the image's acceptance test. Failure modes and mitigations are tabulated in [docs/4_nrp_gitlab.md](docs/4_nrp_gitlab.md#if-the-build-fails). |
| High | Confirm `nids-bgp-control-plane` dependencies once its notebook is committed — there is still no `requirements.txt`. |
| High | Deploy the IYP Neo4j instance and settle the credential model, including the Community Edition RBAC gap above. |
| Medium | `pyspark` is in `requirements.txt` but the base image already ships Spark, so pip installs a second, possibly version-skewed copy over it. Likely wants removing or pinning to the base's Spark version — needs a real Spark session against the DNS notebook to confirm. |
| Medium | Verify NRP egress permits OSDF/`pelicanfs` fetches and S3A reads from `object.openintel.nl` from inside the deployed namespace. |
| Medium | The CI-built image is single-architecture. Decide between pinning `nodeSelector` to `amd64` and building a real multiarch manifest via the buildx variant. |
| Low | Right-size the BGP and DNS memory envelopes against real runs; only telescope's 16/24 Gi is authoritative. |
| Low | Assess the six unassessed assignments for profile and dependency needs. |
