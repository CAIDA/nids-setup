[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [NRP GitLab](4_nrp_gitlab.md) | **JupyterHub**

---

# Deploying One JupyterHub for the NIDS Assignments

This guide deploys a single JupyterHub into your NRP Nautilus namespace via Helm, with **one spawner profile per NIDS assignment**. It is aimed at the instructor/admin standing up a managed course environment for the CAIDA NIDS assignments (BGP control plane, telescope traffic, DNS ecosystem).

> **Alternative — the hosted NRP hub.** Deploying your own hub is optional. Students can instead use the shared hosted service at [https://jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io), logging in via CILogon and picking an appropriately sized instance per assignment (what the assignment READMEs assume). The tradeoff: on the shared hub you lose pinned per-assignment images, shared dataset volumes, roster-based access control, and a stable spawner menu — and you can't shift your server or reach the pre-staged data as directly if there's a problem. Note the hosted service culls a server ~1 hour after the browser disconnects and starts the home directory at 5 GB (extendable on request). Deploy your own hub when you want a managed, reproducible class environment.

## You do NOT need a hub per assignment

A JupyterHub deployment is bound to **one** namespace, **one** hostname, **one** CILogon OAuth application, **one** culling policy, and **one** admin set. The three NIDS assignments differ only in their Python environment and their memory footprint — both of which are **per-profile** (and per-image) settings inside a single hub, not per-hub settings. Running three hubs would triple the CILogon registrations, callback URLs, and configs for no benefit. So: one hub, three profiles.

This pattern extends to additional NIDS assignments (e.g. `nids-asn-introduction`, a prerequisite of the BGP assignment) by adding profile entries.

## Prerequisites

- Completed [Install kubectl](1_kubectl_install.md) — `kubectl` and the `kubelogin` plugin installed.
- Completed [NRP & Namespace](2_nrp_namespace.md) — you are **admin** of an active namespace.
- Completed [Configure kubectl](3_kubectl_config.md) — `kubectl` pointed at your namespace.
- Completed [NRP GitLab](4_nrp_gitlab.md) — the `nids-hub` image built by GitLab CI/CD and present in your registry.
- [Helm](https://helm.sh/docs/intro/install/) installed locally.
- A **CILogon OAuth application** registered at [https://cilogon.org/oauth2/register](https://cilogon.org/oauth2/register) with:
  - Callback URL `https://<HUB_HOST>.nrp-nautilus.io/hub/oauth_callback`
  - Client Type = **Confidential**
  - Scopes = `org.cilogon.userinfo,openid,profile,email`
  - Refresh Tokens = **No**
  - Save the issued **client ID** and **client secret**.

> **Routing note.** NRP is migrating from Ingress to the Gateway API (HTTPRoute); during migration hosts may be exposed on ports **50080/50443** (e.g. `https://<HUB_HOST>.nrp-nautilus.io:50443`). Plain Ingress still works as a temporary path.

## Step 1: Add the JupyterHub Helm Repo

```bash
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update
```

Use chart version **3.3.7** (the version validated for NRP).

## Step 2: Configure `values.yaml`

Start from the annotated template at [configs/values.yaml](../configs/values.yaml) and fill in every `<PLACEHOLDER>`. Its key blocks:

- **`hub.config`** — the CILogon authenticator (client ID/secret, callback, scopes from the Prerequisites) plus the **auth lockdown** (`allowed_idps` + `allowed_domains`, and/or an `allowed_users` roster) and `admin_users`.
- **`cull`** — the mandatory idle-culling policy (see [Mandatory cluster policy](#mandatory-cluster-policy)).
- **`proxy` / `ingress`** — your hostname and TLS (NRP `cert-manager`).
- **`singleuser.image`** — the image the pipeline published in [NRP GitLab](4_nrp_gitlab.md). Pin `tag` to the build's short SHA rather than `latest` when you want a rollout you can verify.
- **`singleuser.profileList`** — the three assignment profiles (see [Spawner profiles](#spawner-profiles)).
- **`singleuser.storage`** — optional shared dataset volume (see [Shared storage](#shared-storage)).

> **Never commit the client secret.** Keep it in an uncommitted override (`helm ... -f configs/values.yaml -f secrets.values.yaml`, with `secrets.values.yaml` git-ignored — this repo's [.gitignore](../.gitignore) covers it) or a Kubernetes secret.

## Step 3: Deploy

```bash
helm upgrade --install jhub jupyterhub/jupyterhub \
  --namespace <YOUR_NAMESPACE> \
  --version 3.3.7 \
  -f configs/values.yaml
```

## Step 4: Verify

```bash
kubectl get pods -n <YOUR_NAMESPACE>
# Confirm culling is actually running (required — see below):
kubectl logs -n <YOUR_NAMESPACE> deployment/jupyterhub -c hub | grep cull
```

Once the hub pod is running, visit your hub's hostname, log in via CILogon, pick a assignment profile, and spawn a server to confirm it works end to end.

## Spawner profiles

All profiles share the one image and differ only by display name and memory envelope. Sizes marked `*` are **estimates** — right-size them against real runs.

| Profile | Memory (guarantee / limit) | Spark? | Notes |
|---|---|---|---|
| NIDS - BGP Control Plane | 4Gi / 8Gi `*` | No | Holds a full RouteViews RIB prefix→ASN map + customer-cone maps in RAM. |
| NIDS - Telescope Traffic | 16Gi / 24Gi | No | **Authoritative:** the assignment requires ≥ 16 GB (24 GB recommended). |
| NIDS - DNS Ecosystem | 8Gi / 12Gi `*` | Yes (`local[*]`) | Spark driver 4G + executor 4G; size the pod above their sum with headroom. |

## Per-assignment notes

### nids-bgp-control-plane
- **Libraries:** `pybgpkit-parser` (import as `pybgpkit_parser`), `pelicanfs`, `pytricia`, `pandas`, `matplotlib`. Pure Python — **no Spark**.
- **Data:** RouteViews RIB (MRT) streamed via **OSDF** from `https://osdf-director.osg-htc.org` (`/routeviews/route-views3/bgpdata/…/RIBS`); CAIDA customer-cone (`ppdc-ases`) and `as2org` from the **in-cluster Ceph** gateway `http://rook-ceph-rgw-nautiluss3.rook/caida/…`.
- **Prerequisite assignment:** `nids-asn-introduction` (ASN / customer-cone concepts) — add a profile for it the same way if you teach it.

### nids-telescope-traffic
- **Libraries:** `dpkt`, `pandas`, `pyarrow`, `pybgpkit-parser`, `pelicanfs`, `pytricia`, `geoip2`, `maxminddb`, `matplotlib`. No Spark.
- **Data:** two anonymized /16 telescope PCAPs and a MaxMind **GeoLite2-City** database, both from **in-cluster Ceph** (`…/caida/ucsd-nt/…` and `…/caida/geolocation/maxmind/…GeoLite2-City.mmdb.gz`) — no MaxMind account needed; RouteViews via OSDF for origin-AS enrichment.
- **Caveat:** highest memory profile; process each capture one at a time (don't hold both flow maps in memory at once).

### nids-dns-ecosystem
- **Libraries:** `pyspark`, `tldextract`, `dnspython` (import as `dns.resolver`), `numpy`, `requests`, `matplotlib`. Spark runs in **local mode** — no standalone/operator Spark cluster.
- **Data:** OpenINTEL forward-DNS zonefile Parquet over **external S3A** at `https://object.openintel.nl` (bucket `openintel-public`, prefix `fdns/basis=zonefile`, anonymous); Anycast Census from `https://manycast.net/api/v1/export/IPv4-latest.parquet`.
- **Caveat:** the Spark config sets `fs.s3a.vectored.io.enabled=false` and `parquet.hadoop.vectored.io.enabled=false` — **leave both false**; enabling them against this object store causes read failures.

## Data access and egress

The datasets split between the in-cluster object store and the public internet, so the hub's namespace must be able to reach both:

| Source | Used by | Reachability |
|---|---|---|
| `rook-ceph-rgw-nautiluss3.rook` (NRP Ceph RGW) | BGP (cones, AS2Org), telescope (PCAPs, GeoLite2) | **In-cluster only** — resolvable from pods inside NRP. |
| `osdf-director.osg-htc.org` (OSDF / RouteViews) | BGP, telescope | External egress. |
| `object.openintel.nl` (OpenINTEL S3A) | DNS | External egress. |
| `manycast.net` | DNS | External egress. |
| Maven Central | DNS (Spark JARs) | External egress — avoided by pre-staging JARs in the image (see [NRP GitLab](4_nrp_gitlab.md)). |

## Mandatory cluster policy

These are **required** by NRP — a deployment missing them can get your namespace locked:

- **Culling.** Not optional. Configure a `cull` block with `timeout` ≤ 21600 (6 hours); the template uses `timeout: 3600`, `every: 600`, `maxAge: 0`. Verify after deploy with the `grep cull` command in Step 4.
- **Auth lockdown.** Do not leave the hub open. Restrict via `allowed_idps` (your institution's IdP EntityID from [https://cilogon.org/idplist](https://cilogon.org/idplist)) with matching `allowed_domains`, and/or an `allowed_users` allowlist for a small roster.
- **Admins.** Add the NRP admin users to `admin_users` for support/debugging. If you use an IdP allowlist, **include UCSD** so NRP admins and CAIDA content owners can authenticate.

## Shared storage

To hand the same fixed datasets to a whole class, attach a PVC via `singleuser.storage.extraVolumes` / `extraVolumeMounts` (e.g. mounted read-only at `/home/shared`). Multi-pod use requires an access mode of **ReadOnlyMany** or **ReadWriteMany**; a read-only shared volume fits handing out immutable datasets (telescope PCAPs, cached OpenINTEL/RIB data). See the commented block in [configs/values.yaml](../configs/values.yaml).

## Operational good practice

- Keep `values.yaml` under version control in NRP GitLab and auto-redeploy on change via the [k8s GitLab integration](https://nrp.ai/documentation/userdocs/development/k8s-integration/). Pushing to the `nrp` remote from [NRP GitLab](4_nrp_gitlab.md) is the entry point for this.
- Maintain a running doc of the hub setup, per-assignment profiles, and workflows for maintainers.

## Before you go live (confirm)

- **Right-size memory** for the BGP and DNS profiles against real runs (telescope's 16/24 Gi is authoritative; the others are estimates).
- **Spark JARs:** confirm they are pre-staged in the image (they are, in [image/Dockerfile](../image/Dockerfile) — the pipeline log shows the two `curl` fetches), or that NRP pod egress to Maven Central is permitted at Spark session start.
- **Egress/reachability:** confirm the namespace can reach in-cluster `rook-ceph-rgw-nautiluss3.rook` and the external hosts (OSDF, `object.openintel.nl`, `manycast.net`).
- **Base image:** confirm the Spark-capable base carries a Python compatible with the pinned dependencies.

## Troubleshooting

- **Pod stuck in `Pending`** — check `kubectl describe pod <pod> -n <YOUR_NAMESPACE>` for resource-quota or scheduling issues (the telescope profile needs a node that can satisfy 16–24 Gi).
- **OAuth callback mismatch** — ensure the callback URL registered with CILogon exactly matches your hub's hostname and path.
- **DNS S3A read failures** — verify `fs.s3a.vectored.io.enabled` and `parquet.hadoop.vectored.io.enabled` are both `false`.
- **Can't reach CAIDA data** — the `rook-ceph-rgw-nautiluss3.rook` endpoint only resolves inside the cluster; it won't work from a laptop.
- **`ImagePullBackOff` or `exec format error`** — the image isn't pullable (private registry without a pull secret) or was built for the wrong CPU architecture; see [NRP GitLab](4_nrp_gitlab.md).

## References

- [NRP Documentation: Deploy JupyterHub](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub/)
- [NRP hosted JupyterHub Service](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub-service/)
- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [CILogon OAuth registration](https://cilogon.org/oauth2/register) · [CILogon IdP list](https://cilogon.org/idplist)
- Supporting files in this repo: [image/Dockerfile](../image/Dockerfile), [image/requirements.txt](../image/requirements.txt), [configs/values.yaml](../configs/values.yaml)

---

[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [NRP GitLab](4_nrp_gitlab.md) | **JupyterHub**
