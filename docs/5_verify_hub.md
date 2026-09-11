[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [JupyterHub](4_nrp_jupyterhub.md) | **Verify**

---

# Verify the Hub Works

> **Path: everyone — but not the same amount of it.**
> **Community hub** — Steps 1–3 only, in their community-hub form: spawn a server, upload the
> notebook, run it. Skip Step 5 (no spawner profiles to repeat across) and the `kubectl` lookups.
> **Your own hub** — the whole guide, Steps 1–6.
> Which path you are on was decided [here](../README.md#running-on-nrp).

`helm upgrade` returning and `kubectl get pods` showing `Running` prove the hub *deployed*. Neither
proves the thing that matters: that inside a spawned server the dependencies import, the memory
limit is what the profile promised, and the datasets are actually reachable. Every failure in this
guide is invisible to `kubectl` and obvious the moment a student hits it — and that is as true of
the community hub, which you did not deploy and cannot inspect, as of one you built yourself.

Two notebooks do the checking, and both are for you, not for students:

| Notebook | Where | Answers |
|---|---|---|
| [notebooks/test.ipynb](../notebooks/test.ipynb) | this repo | Is the **hub** sound? Run once per spawner profile, after every deploy. |
| `00-environment-check.ipynb` | each **answer-key** repo | Are **that assignment's** datasets and libraries reachable? Run before handing the assignment out. |

Each ends in one line — `JupyterHub is ready` (or `... ready for nids-<assignment>`), or a list of
what failed.

## Prerequisites

**Community hub**

- An active NRP namespace from [NRP & Namespace](2_nrp_namespace.md) Steps 1–3, and a CILogon login
  that reaches [jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io).

**Your own hub**

- Completed [JupyterHub](4_nrp_jupyterhub.md) — the hub is deployed and its hostname resolves.
- You can log in through CILogon with the OAuth application from
  [doc 2 Step 5](2_nrp_namespace.md#step-5-register-a-cilogon-oauth-application) and reach the
  spawner menu. Your identity provider must be one the hub's `allowed_idps` / `allowed_domains`
  permit.

## Step 1: Spawn a server

**Community hub.** Log in at
[jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io) and pick an instance
sized for the assignment you are checking — the assignment's README gives the number, and the
telescope assignment's **≥ 16 GB** is the one you cannot get wrong. Then go to Step 2; the rest of
this step is own-hub only.

**Your own hub.** Visit `https://<HUB_HOST>.nrp-nautilus.io` — e.g. `https://caida-nids-jhub.nrp-nautilus.io`.
`HUB_HOST` is the subdomain you claimed in
[NRP & Namespace](2_nrp_namespace.md#step-4-your-hubs-hostname-hub_host), which is also where the naming
rules and worked examples live; it is set as `ingress.hosts` in
[configs/values.yaml](../configs/values.yaml). During the Gateway API migration it may instead be
`https://<HUB_HOST>.nrp-nautilus.io:50443` — see the routing note in
[doc 4](4_nrp_jupyterhub.md). Log in, pick a profile, and start it.

To confirm the hostname the cluster is actually serving:

```bash
kubectl get ingress -n <YOUR_NAMESPACE>
```

If the pod never reaches `Running`, stop here — that is a deployment problem, not an environment
one. Check `kubectl describe pod <pod> -n <YOUR_NAMESPACE>` and see
[Troubleshooting in doc 4](4_nrp_jupyterhub.md#troubleshooting).

## Step 2: Get the notebook into the server

Both methods work on both hubs.

**Upload** — the simplest, and the one to use on the community hub. Drag
[notebooks/test.ipynb](../notebooks/test.ipynb) from your laptop onto the JupyterLab file browser
(the left-hand pane), or use the ⬆ upload button above it.

**Or clone** — in JupyterLab, *File → New → Terminal*, then:

```bash
git clone https://github.com/CAIDA/nids-setup.git
```

and open `nids-setup/notebooks/test.ipynb` from the file browser.

## Step 3: Run it

*Run → Run All Cells*, then read the last line.

The `%pip install` cell is the union of [image/requirements.txt](../image/requirements.txt). On your
own hub's `nids-hub` image every package is already present and the cell is a no-op — that no-op is
itself part of what you are verifying. On the community hub it installs for real and can take
several minutes.

A healthy run on **your own hub** looks like this:

```
--- shared: what every NIDS assignment needs ---

[ ok ] python and kernel  (python 3.12.7)
[ ok ] home directory is writable  (8.9 GiB free)
[ ok ] memory and cpu  (24.0 GiB limit, 8 cpu)
[ ok ] shared imports  (pandas 2.2.3, numpy 1.26.4)
[ ok ] external egress (pypi)  (HTTP 200)
[ ok ] public dns resolution
[ ok ] in-cluster ceph gateway  (HTTP 200, as2org.jsonl 41 MiB)

--- nids-hub image extras (informational on the hosted NRP hub) ---

[ ok ] pre-staged spark s3a jars  (bundle-2.24.6.jar, hadoop-aws-3.4.0.jar)
[ ok ] spark session (local[*])  (spark 4.2.0)

JupyterHub is ready
```

**On the community hub**, expect the same block above the divider — including
`in-cluster ceph gateway`, which passes because the server is still running inside NRP — and expect
the two rows below it to come back as **warnings** rather than `[ ok ]`: the stock image has no
pre-staged jars and no JVM. That only matters for the DNS assignment, and only as slower Spark
startup (the jars are then fetched from Maven Central). Everything else failing is a real failure.

## Step 4: What each failure means

The "where to look" column is written for your own hub. **On the community hub** you have no
`values.yaml`, no image, and no `kubectl` access to the hub's namespace, so the rows about the PVC,
`profileList`, and the image do not apply — there, `memory and cpu` reporting the wrong size means
you picked the wrong instance size at spawn, and a `shared imports` failure means the `%pip` cell
did not finish. The egress and Ceph rows apply on both.

| Failed check | Likely cause | Where to look |
|---|---|---|
| `home directory is writable` | The home PVC never bound, or it is full. | `kubectl get pvc -n <NS>`; `singleuser.storage.capacity` in [values.yaml](../configs/values.yaml) |
| `memory and cpu` reports the wrong size | `kubespawner_override` didn't apply, or you picked a different profile than you think. | `singleuser.profileList` in [values.yaml](../configs/values.yaml); [Spawner profiles](4_nrp_jupyterhub.md#spawner-profiles) |
| `shared imports` | The pod is running some *other* image, or the build didn't include `requirements.txt`. | `kubectl describe pod <pod> -n <NS>` and compare the image digest; [Build the images](0_build_images.md) |
| `external egress (pypi)` / `public dns resolution` | Namespace egress or cluster DNS is blocked. | [Data access and egress](4_nrp_jupyterhub.md#data-access-and-egress) |
| `in-cluster ceph gateway` — did not resolve | You are not running inside NRP. `rook-ceph-rgw-nautiluss3.rook` resolves only from pods in the cluster. | Run the notebook on the hub, not on your laptop |
| `in-cluster ceph gateway` — resolved but non-2xx | The gateway is up but the object moved, or a NetworkPolicy blocks the namespace. | [Data access and egress](4_nrp_jupyterhub.md#data-access-and-egress) |
| `pre-staged spark s3a jars` (warning) | Not the `nids-hub` image — expected on the hosted NRP hub. Spark will then pull the jars from Maven Central at session start, which needs egress. | the two `curl` fetches in [image/Dockerfile](../image/Dockerfile) |
| `spark session (local[*])` (warning) | No JVM, i.e. not a Spark-capable base image. Only the DNS assignment needs it. | [image/Dockerfile](../image/Dockerfile) |

Two failures happen *before* the notebook can run at all, so you will see them in `kubectl`, not in
the output above: `ImagePullBackOff` (image not pullable — a private registry with no pull secret)
and `exec format error` (image built for the wrong CPU architecture). Both are covered in
[If the build fails](0_build_images.md#if-the-build-fails).

## Step 5: Repeat per profile

**Your own hub only — skip this on the community hub**, which has no spawner profiles to repeat
across (you choose an instance size per session instead, and Step 1 already covered picking the
right one).

Run it once for **each** entry in `singleuser.profileList`. The image is shared, so the imports and
egress results will not change — the memory envelope will, and that is the number worth confirming
against a real pod rather than against the value you typed into `values.yaml`.

## Step 6: Confirm each assignment is ready

**Both paths, if you are handing an assignment to students** — the datasets and the egress they need
are the same either way, and the community hub gives you no other way to find out.

Before releasing an assignment, run its check on the profile (or, on the community hub, the instance
size) that assignment will use. Clone the
answer-key repo into the hub (the clone URLs are the *answer key* links in the ETP overview README)
and run its `00-environment-check.ipynb`:

```bash
git clone https://github.com/CAIDA/nids-dns-ecosystem-key.git
```

| Answer-key repo | Profile to run it on | What it actually touches | Time |
|---|---|---|---|
| `nids-asn-introduction-key` | BGP | Ceph: `as2org.jsonl` parses, `ppdc-ases` is a bz2 stream. Standard library only — no `%pip`. | seconds |
| `nids-bgp-control-plane-key` | BGP | OSDF RIB *listing* for `route-views3`, plus the two Ceph objects above. No RIB is parsed. | seconds |
| `nids-irr-rpki-whois-key` | BGP | Ceph IRR dump + RouteViews prefix2as, and a HEAD against **`ftp.ripe.net`** — the only assignment that reads from RIPE. | seconds |
| `nids-itdk-key` | BGP | Your **Postgres** instance: credentials resolve, `SELECT 1`, the four `caida_itdk` tables exist, one row reads. Needs `db_credentials.env` uploaded next to the notebook. | seconds |
| `nids-dns-ecosystem-key` | DNS (Spark) | Starts Spark with the assignment's exact S3A config, reads one OpenINTEL partition's Parquet **schema**, HEADs `manycast.net`, resolves a hostname via `dnspython`. | 2–5 min |
| `nids-telescope-traffic-key` | Telescope (24 GB) | **Fails if memory < 16 GiB**, then the two Ceph PCAPs, the GeoLite2 database, and an OSDF RIB listing. | seconds |

A green run there is the signal the assignment is ready to hand out. A red one tells you which
host your namespace cannot reach — compare it against the egress table in
[Deploy JupyterHub](4_nrp_jupyterhub.md#data-access-and-egress).

## Troubleshooting

- **`ModuleNotFoundError: No module named 'bgpkit'`** — the package is `pybgpkit-parser` and imports
  as `pybgpkit_parser`. Not a hub problem.
- **DNS check: S3A read fails** — confirm `fs.s3a.vectored.io.enabled` and
  `parquet.hadoop.vectored.io.enabled` are both `false`. Enabling them against this object store
  breaks reads; the check notebook sets them correctly, so a failure here means something else
  changed them.
- **DNS check: Spark hangs at session start** — `spark.jars.packages` resolves through Ivy on first
  run and needs Maven Central. The pre-staged jars in `$SPARK_HOME/jars` do not skip that
  resolution.
- **ITDK check: "no ITDK_READ_DSN"** — copy `db_credentials.env.example` to `db_credentials.env`,
  fill in the read-only user, and upload it next to the notebook. The check never prints the DSN.
- **A check hangs instead of failing** — every HTTP call has a 60-second timeout, so give it a
  minute before interrupting; the OSDF listing and the Spark start are the two slow ones.

## References

- [Deploy JupyterHub](4_nrp_jupyterhub.md) — the deployment this verifies
- [Build the images](0_build_images.md) — image build and its failure modes

---

[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [JupyterHub](4_nrp_jupyterhub.md) | **Verify**
