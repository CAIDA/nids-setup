[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | **JupyterHub** | [Verify](5_verify_hub.md)

---

# Deploying One JupyterHub for the NIDS Assignments

This guide deploys a single JupyterHub into your NRP Nautilus namespace via Helm, with **one spawner profile per NIDS assignment**. It is aimed at the instructor/admin standing up a managed course environment for the CAIDA NIDS assignments (BGP control plane, telescope traffic, DNS ecosystem).

> **Path: your own hub — skip this entire guide on the community hub.** Deploying a hub is
> optional. The alternative is NRP's hosted service at
> [jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io): log in via CILogon,
> pick an instance sized for the assignment you are running (what the assignment READMEs assume),
> and go straight to [Verify](5_verify_hub.md). Nothing below applies there — no `values.yaml`, no
> Helm, no CILogon registration of your own.
>
> The tradeoff on the hosted hub: no pinned per-assignment image (each assignment `%pip install`s
> its deps, taking minutes), no JVM for the DNS assignment's Spark, no shared dataset volume, no
> roster-based access control, and no stable spawner menu — you re-pick the instance size by hand
> every time. It also culls a server ~1 hour after the browser disconnects and starts the home
> directory at 5 GB (extendable on request). Deploy your own hub when you want a managed,
> reproducible class environment. See the
> [full comparison](../README.md#start-here-whose-hub-will-you-use).

## You do NOT need a hub per assignment

A JupyterHub deployment is bound to **one** namespace, **one** hostname, **one** CILogon OAuth application, **one** culling policy, and **one** admin set. The three NIDS assignments differ only in their Python environment and their memory footprint — both of which are **per-profile** (and per-image) settings inside a single hub, not per-hub settings. Running three hubs would triple the CILogon registrations, callback URLs, and configs for no benefit. So: one hub, three profiles.

This pattern extends to additional NIDS assignments (e.g. `nids-asn-introduction`, a prerequisite of the BGP assignment) by adding profile entries.

## Prerequisites

- Completed [Install kubectl](1_kubectl_install.md) — `kubectl` and the `kubelogin` plugin installed.
- Completed [NRP & Namespace](2_nrp_namespace.md) **including its own-hub-only Steps 4–5** — you are **admin** of an active namespace, you have pinned your [`HUB_HOST`](2_nrp_namespace.md#step-4-your-hubs-hostname-hub_host), and you have a [registered CILogon OAuth application](2_nrp_namespace.md#step-5-register-a-cilogon-oauth-application) with its **client ID** and **client secret** to hand.
- Completed [Configure kubectl](3_kubectl_config.md) — `kubectl` pointed at your namespace.
- The published `nids-hub` image path, for `singleuser.image` below. The image is already built — you only need to [build it yourself](0_build_images.md) if you are changing it.
- [Helm](https://helm.sh/docs/intro/install/) installed locally.

> **Routing note.** NRP is migrating from Ingress to the Gateway API (HTTPRoute); during migration hosts may be exposed on ports **50080/50443** (e.g. `https://<HUB_HOST>.nrp-nautilus.io:50443`). Plain Ingress still works as a temporary path.

## Step 1: Add the JupyterHub Helm Repo

```bash
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update
```

Use chart version **3.3.7** (the version validated for NRP).

## Step 2: Configure `values.yaml`

Start from the annotated template at [configs/values.yaml](../configs/values.yaml) and fill in every `<PLACEHOLDER>`. Its key blocks:

- **`hub.config`** — the CILogon authenticator (the client ID/secret, callback URL, and scopes from [doc 2 Step 5](2_nrp_namespace.md#step-5-register-a-cilogon-oauth-application)) plus the **auth lockdown** (`allowed_idps` + `allowed_domains`, and/or an `allowed_users` roster) and `admin_users`.
- **`cull`** — the mandatory idle-culling policy (see [Mandatory cluster policy](#mandatory-cluster-policy)).
- **`proxy` / `ingress`** — your hostname and TLS (NRP `cert-manager`).
- **`singleuser.image`** — the published hub image (see [Build the images](0_build_images.md) for where it comes from). Pin `tag` to the build's short SHA rather than `latest` when you want a rollout you can verify.
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

Once the hub pod is running, visit your hub's hostname, log in via CILogon, pick a assignment profile, and spawn a server. `Running` is not the same as *working*, though — for the checks `kubectl` cannot make (do the dependencies import, is the memory envelope real, are the datasets reachable), continue to [Verify the hub works](5_verify_hub.md).

## Spawner profiles

All profiles share the one image and differ only by display name and memory envelope. Sizes marked `*` are **estimates** — right-size them against real runs.

| Profile | Memory (guarantee / limit) | Spark? | Notes |
|---|---|---|---|
| NIDS - BGP Control Plane | 4Gi / 8Gi `*` | No | Holds a full RouteViews RIB prefix→ASN map + customer-cone maps in RAM. |
| NIDS - Telescope Traffic | 16Gi / 24Gi | No | **Authoritative:** the assignment requires ≥ 16 GB (24 GB recommended). |
| NIDS - DNS Ecosystem | 8Gi / 12Gi `*` | Yes (`local[*]`) | Spark driver 4G + executor 4G; size the pod above their sum with headroom. |

## Per-assignment notes

Dataset paths, provenance, and provisioning are **not** repeated here — they live in
[datasets/](../datasets/README.md), one directory per dataset, because most are shared between
assignments. What follows is only what bears on the hub itself.

### nids-bgp-control-plane (BGP)
- **Libraries:** `pybgpkit-parser` (import as `pybgpkit_parser`), `pelicanfs`, `py-radix`, `pandas`, `matplotlib`. Pure Python — **no Spark**.
- **Data:** [routeviews-bgp-rib](../datasets/routeviews-bgp-rib/), [caida-as-customer-cone](../datasets/caida-as-customer-cone/), [caida-as2org](../datasets/caida-as2org/).
- **Prerequisite assignment:** `nids-asn-introduction` (ASN) — reads the same two Ceph objects; add a profile for it the same way if you teach it.

### nids-telescope-traffic (TELESCOPE)
- **Libraries:** `dpkt`, `pandas`, `pyarrow`, `pybgpkit-parser`, `pelicanfs`, `py-radix`, `geoip2`, `maxminddb`, `matplotlib`. No Spark.
- **Data:** [ucsd-nt-pcap-samples](../datasets/ucsd-nt-pcap-samples/), [maxmind-geolite2](../datasets/maxmind-geolite2/), [routeviews-bgp-rib](../datasets/routeviews-bgp-rib/) for origin-AS enrichment.
- **Caveat:** highest memory profile; process each capture one at a time (don't hold both flow maps in memory at once).

### nids-dns-ecosystem (DNS)
- **Libraries:** `pyspark`, `tldextract`, `dnspython` (import as `dns.resolver`), `numpy`, `requests`, `matplotlib`. Spark runs in **local mode** — no standalone/operator Spark cluster.
- **Data:** [openintel-fdns](../datasets/openintel-fdns/), [anycast-census](../datasets/anycast-census/).
- **Caveat:** the Spark config sets `fs.s3a.vectored.io.enabled=false` and `parquet.hadoop.vectored.io.enabled=false` — **leave both false**; enabling them against this object store causes read failures.

## Data access and egress

The datasets split between the in-cluster object store and the public internet, so the hub's namespace must be able to reach both. Assignment codes are the ones published on the [NIDS assignments page](https://www.caida.org/projects/nids/assignments/); what each dataset is, and which of them are behind each host, is in [datasets/](../datasets/README.md).

| Source | Used by | Reachability |
|---|---|---|
| `rook-ceph-rgw-nautiluss3.rook` (NRP Ceph RGW) | ASN, BGP, IRR, TELESCOPE | **In-cluster only** — resolvable from pods inside NRP. |
| `publicdata.caida.org` (CAIDA as2org) | ASN, BGP | External egress. **[unverified]** — newly
required: `nids-setup.py data` stages as2org from the pinned public release in **both** modes,
because the in-cluster object is undated and would otherwise make the hub and a laptop
disagree on the country figures. Confirm with `notebooks/check-datasets.ipynb` on the hub. |
| `osdf-director.osg-htc.org` (OSDF / RouteViews) | BGP, TELESCOPE | External egress. |
| `ftp.ripe.net` (RIPE RPKI ROAs) | IRR | External egress — the only assignment reaching this host. |
| `object.openintel.nl` (OpenINTEL S3A) | DNS | External egress. |
| `manycast.net` | DNS | External egress. |
| `iyp-bolt.ihr.live:7687` (IYP, Bolt) | IYP | External egress — Bolt, not HTTP. |
| Maven Central | DNS (Spark JARs) | External egress — avoided by pre-staging JARs in the image (see [image/Dockerfile](../image/Dockerfile)). |

Confirm all of it in one run from inside a spawned server with [notebooks/check-datasets.ipynb](../notebooks/check-datasets.ipynb).

## Mandatory cluster policy

These are **required** by NRP — a deployment missing them can get your namespace locked:

- **Culling.** Not optional. Configure a `cull` block with `timeout` ≤ 21600 (6 hours); the template uses `timeout: 3600`, `every: 600`, `maxAge: 0`. Verify after deploy with the `grep cull` command in Step 4.
- **Auth lockdown.** Do not leave the hub open. Restrict via `allowed_idps` (your institution's IdP EntityID from [https://cilogon.org/idplist](https://cilogon.org/idplist)) with matching `allowed_domains`, and/or an `allowed_users` allowlist for a small roster.
- **Admins.** Add the NRP admin users to `admin_users` for support/debugging. If you use an IdP allowlist, **include UCSD** so NRP admins and CAIDA content owners can authenticate.

## Shared storage

To hand the same fixed datasets to a whole class, attach a PVC via `singleuser.storage.extraVolumes` / `extraVolumeMounts` (e.g. mounted read-only at `/home/shared`). Multi-pod use requires an access mode of **ReadOnlyMany** or **ReadWriteMany**; a read-only shared volume fits handing out immutable datasets (telescope PCAPs, cached OpenINTEL/RIB data). See the commented block in [configs/values.yaml](../configs/values.yaml).

## Operational good practice

- Keep your filled-in `values.yaml` under version control (secrets excluded — see the note in Step 2) so a redeploy is reproducible and changes are reviewable.
- Maintain a running doc of the hub setup, per-assignment profiles, and workflows for maintainers.

## Before you go live (confirm)

- **Right-size memory** for the BGP and DNS profiles against real runs (telescope's 16/24 Gi is authoritative; the others are estimates).
- **Spark JARs:** confirm they are pre-staged in the image (they are — the two `curl` fetches in [image/Dockerfile](../image/Dockerfile)), or that NRP pod egress to Maven Central is permitted at Spark session start.
- **Egress/reachability:** confirm the namespace can reach in-cluster `rook-ceph-rgw-nautiluss3.rook` and the external hosts (OSDF, `ftp.ripe.net`, `object.openintel.nl`, `manycast.net`, `iyp-bolt.ihr.live`). [notebooks/check-datasets.ipynb](../notebooks/check-datasets.ipynb) answers this in one run.
- **Base image:** confirm the Spark-capable base carries a Python compatible with the pinned dependencies.

## Troubleshooting

- **Pod stuck in `Pending`** — check `kubectl describe pod <pod> -n <YOUR_NAMESPACE>` for resource-quota or scheduling issues (the telescope profile needs a node that can satisfy 16–24 Gi).
- **OAuth callback mismatch** — ensure the callback URL registered with CILogon exactly matches your hub's hostname and path.
- **DNS S3A read failures** — verify `fs.s3a.vectored.io.enabled` and `parquet.hadoop.vectored.io.enabled` are both `false`.
- **Can't reach CAIDA data** — the `rook-ceph-rgw-nautiluss3.rook` endpoint only resolves inside the cluster; it won't work from a laptop. Run [notebooks/check-datasets.ipynb](../notebooks/check-datasets.ipynb) from inside a spawned server to see which datasets are actually reachable.
- **RPKI fetches fail but everything else works** — `nids-irr-rpki-whois` is the only assignment reaching `ftp.ripe.net`, so a namespace whose egress permits CAIDA and OSDF but not RIPE fails there and nowhere else.
- **`ImagePullBackOff` or `exec format error`** — the image isn't pullable (private registry without a pull secret) or was built for the wrong CPU architecture; see [Build the images](0_build_images.md#if-the-build-fails).

## References

- [NRP Documentation: Deploy JupyterHub](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub/)
- [NRP hosted JupyterHub Service](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub-service/)
- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [CILogon OAuth registration](https://cilogon.org/oauth2/register) · [CILogon IdP list](https://cilogon.org/idplist)
- Supporting files in this repo: [image/Dockerfile](../image/Dockerfile), [image/requirements.txt](../image/requirements.txt), [configs/values.yaml](../configs/values.yaml)

---

[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | **JupyterHub** | [Verify](5_verify_hub.md)
