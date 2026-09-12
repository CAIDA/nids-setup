# Building and Publishing the Hub Image

> **Maintainers only.** Most readers do not need this page: the deployment guides start at
> [Install kubectl](1_kubectl_install.md), and a hub configured with an image path only needs to
> *pull* it. You need this page when you **publish** the image — standing up a hub against a
> registry of your own — or when you **change** it: a new Python dependency, a new module, or a
> base-image bump.

The JupyterHub in [JupyterHub](4_nrp_jupyterhub.md) runs a **single combined container image** shared
by every NIDS assignment profile. Its sources are two files in this repo —
[image/Dockerfile](../image/Dockerfile) and [image/requirements.txt](../image/requirements.txt) — and
this guide builds them with Docker and pushes the result to a container registry the NRP cluster can
pull from.

## Prerequisites

- **Docker with `buildx`.** Bundled with Docker Desktop; on Linux install the `docker-buildx-plugin`
  package. Check with `docker buildx version`.
- **A container registry account** you can push to, and which the cluster can pull from — see
  [Step 1](#step-1-choose-the-image-path).
- **~20 GB of free disk on the host**, not just inside Docker's VM. The Spark base alone is
  multi-gigabyte before your layers, and on macOS `Docker.raw` grows on demand — so a full host disk
  fails the build even though `docker system df` looks fine. Check with `df -h`.
- A clone of this repo. The build reads `image/`; nothing else is needed.

## Step 1: Choose the image path

Pick where the image lives and set it once for the whole session — every command below reuses it:

```bash
export IMAGE=caida/nids-hub
```

Two registries make sense here:

| Registry | `IMAGE` value | Notes |
|---|---|---|
| **Docker Hub** | `caida/nids-hub` | Simplest. A **public** repo needs no pull credentials on the cluster. Anonymous pulls are rate-limited, but generously enough for a class. |
| **GHCR** | `ghcr.io/caida/nids-hub` | Lives beside the source on GitHub, no separate account, no pull rate limits. Package visibility is set per-package in GitHub and defaults to **private**. |

**Prefer a public repo.** A private one works, but every namespace that deploys the hub then needs a
pull secret — see [Letting the hub pull a private image](#letting-the-hub-pull-a-private-image).

Whatever you choose has to match `singleuser.image.name` in
[configs/values.yaml](../configs/values.yaml) (that is [Step 5](#step-5-point-the-hub-at-the-tag)).

## Step 2: Log in to the registry

Docker Hub:

```bash
docker login
```

GHCR — the password is a [GitHub personal access token](https://github.com/settings/tokens) with the
`write:packages` scope, **not** your account password:

```bash
docker login ghcr.io -u <your-github-username>
```

Either way the credential is stored by Docker in `~/.docker/config.json` and nothing lands in this
repo.

## Step 3: Build and push

Use the wrapper — it derives the tags and passes the flags that are easy to forget. Run it from the
repo root; it picks up the `IMAGE` you exported in Step 1:

```bash
scripts/build-push.sh
```

It publishes two tags: `latest`, and the current commit's short SHA. That is all there is to it, but
the script is not a black box — this is the command it runs:

```bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  -t "$IMAGE:$(git rev-parse --short HEAD)" \
  -t "$IMAGE:latest" \
  --push image/
```

Three things in there are load-bearing:

- **`--platform linux/amd64` is not optional.** NRP's nodes are predominantly x86, and an arm64 image
  fails at pod start with `exec format error` — a failure that surfaces only when a student tries to
  spawn a server. Always build amd64, whatever your laptop is.
- **On Apple Silicon that means QEMU emulation, so expect a slow first build.** Installing the
  Spark dependency set under emulation takes far longer than native — `pyspark` alone is a large
  source distribution. It does work. If the wait is unacceptable, build on an x86 host or attach a
  remote amd64 builder (`docker buildx create --name amd64 --driver docker-container <remote> --use`).
  Note that since `pytricia` was replaced by `py-radix` (2026-09-04) **nothing in
  `requirements.txt` compiles**: every package is either pure Python or has an amd64 wheel, so the
  old "compiling a C extension under emulation" cost is gone. `scripts/check-wheels.py` re-checks
  that claim.
- **`--provenance=false`** keeps the push a plain single-architecture manifest. Without it `buildx`
  attaches attestations and publishes an image index instead, which some registry and container-runtime
  combinations handle poorly.
- **The build context is `image/`, not the repo root.** `COPY requirements.txt` in the Dockerfile is
  relative to that.

The first build takes tens of minutes: Docker pulls and unpacks the multi-gigabyte Spark base,
compiles the Python dependencies, downloads the Spark S3A JARs, then pushes the result. Later builds
reuse the layer cache and only redo what changed after the first edited layer.

## Step 4: Verify the image

Locally, that the dependency set imports:

```bash
docker run --rm --platform linux/amd64 "$IMAGE:latest" \
  python -c "import pyspark, dpkt, radix, pybgpkit_parser, pelicanfs, neo4j; print('ok')"
```

Then from the cluster, which additionally proves the pull path and the CPU architecture:

```bash
kubectl run nids-hub-smoke -n <YOUR_NAMESPACE> --rm -it --restart=Never \
  --image="$IMAGE:latest" \
  --command -- python -c "import pyspark, dpkt, radix, pybgpkit_parser, pelicanfs, neo4j; print('ok')"
```

> `ImagePullBackOff` means the cluster can't pull the image — either the repo is private and has no
> pull secret yet (see [Letting the hub pull a private image](#letting-the-hub-pull-a-private-image)),
> or the tag isn't published. `exec format error` means the image was built for the wrong CPU
> architecture (see [If the build fails](#if-the-build-fails)).

## Step 5: Point the hub at the tag

Set `singleuser.image` in [configs/values.yaml](../configs/values.yaml) to what you just published:

```yaml
singleuser:
  image:
    name: caida/nids-hub
    tag: latest
```

> **Pin the tag, not `latest`.** `latest` is mutable, and Kubernetes defaults to
> `imagePullPolicy: IfNotPresent`, so a node that already cached `latest` will keep serving the _old_
> image. When you need a rollout you can prove happened, set `tag` to the build's short SHA — the
> script prints it.

## What's in the image

All profiles share **one combined image** — the dependency sets are additive, and only the DNS
assignment needs Spark. Python dependencies come from [image/requirements.txt](../image/requirements.txt),
the union of the assignments' imports.

The image also pre-stages the DNS assignment's Spark S3A JARs (`hadoop-aws:3.4.0`,
`software.amazon.awssdk:bundle:2.24.6`) so a Spark session doesn't depend on Maven Central egress at
startup — see [image/Dockerfile](../image/Dockerfile). The base image is pinned by digest rather than
`:latest`, because a moving base invalidates the whole build cache.

> Split the DNS/Spark image off from a plain BGP+telescope image **only** if the combined image
> becomes unwieldy or a real version-pin conflict appears.

## Rebuilding and versioning

Edit anything under `image/`, commit, then rerun the build:

```bash
git commit -am "image: add <dependency>"
scripts/build-push.sh
```

Commit **before** building: the SHA tag comes from `HEAD`, so building with uncommitted changes
produces a tag that doesn't describe its contents. The script warns when `image/` is dirty.

Each build adds a SHA tag plus layers, all multi-gigabyte, and NRP does **not** back up container
images. Prune old tags in your registry periodically, keeping `latest` and the most recent few SHAs.

## Letting the hub pull a private image

Skip this if the repo is public. Otherwise every namespace deploying the hub needs a pull secret:

```bash
kubectl create secret docker-registry regcred -n <YOUR_NAMESPACE> \
  --docker-server=<REGISTRY_HOST> \
  --docker-username=<USERNAME> \
  --docker-password=<TOKEN>
```

`<REGISTRY_HOST>` is `https://index.docker.io/v1/` for Docker Hub or `ghcr.io` for GHCR. Use a
scoped, revocable token as the password — a GitHub PAT with `read:packages` for GHCR, a Docker Hub
access token for Docker Hub — not an account password.

Then uncomment the `imagePullSecrets` stanza in [configs/values.yaml](../configs/values.yaml). Use
the chart's **top-level** `imagePullSecrets`, not `singleuser.image.pullSecrets` — the hub, the user
pods, _and_ the chart's image puller all need the credential.

## If the build fails

This image has not yet been built end to end, so treat the first run as its acceptance test.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `error: command 'gcc' failed` | a source-only dependency needs a compiler the base lacks | Add `build-essential` in a root `RUN apt-get` layer before the pip install |
| `exec format error` at pod start | Image built for the wrong CPU architecture | You omitted `--platform linux/amd64`; rebuild with it. Optionally also pin `nodeSelector` to `amd64` in `values.yaml` |
| Build crawls on Apple Silicon | `linux/amd64` runs under QEMU emulation | Expected. Build on an x86 host, or attach a remote amd64 builder with `docker buildx create` |
| `no space left on device` | Extracted base + compiled deps + JARs need well over 10 GB | `docker system prune -a` and raise Docker Desktop's disk image size (Settings → Resources) |
| `error committing ...: write /var/lib/docker/buildkit/metadata_v2.db: input/output error`, often with `Failed to remove contents in a temporary directory` just before it, and Docker unresponsive afterwards | **The host disk is full**, not Docker's VM. On macOS `Docker.raw` grows on demand, so buildkit hits an I/O error rather than a clean `ENOSPC`. this is what a real build attempt hit here, with 16 GiB free on the host | `df -h` first. Free host space, then `docker system prune -a`. Docker Desktop may need a restart to recover |
| `denied: requested access to the resource is denied` | Not logged in, or `IMAGE` names a namespace you can't push to | Rerun [Step 2](#step-2-log-in-to-the-registry); confirm `IMAGE` matches your registry account |
| Push stalls or dies partway | A multi-GB layer over a slow uplink | Rerun the script — `docker push` resumes from the layers already accepted |
| Every rebuild is slow, not just the first | The base image moved, invalidating the layer cache | The base is digest-pinned in [image/Dockerfile](../image/Dockerfile); bump it deliberately, not incidentally |
| `toomanyrequests` pulling the base | Anonymous registry rate limit on `quay.io` | Wait, or authenticate to the base registry |

> **Open item:** `pyspark` is listed in [image/requirements.txt](../image/requirements.txt), but the
> base image already ships Spark — pip installs a second, possibly version-skewed copy. It likely
> wants removing, pending a real Spark session against the DNS notebook to confirm.

## Next

With the image published, [JupyterHub](4_nrp_jupyterhub.md) deploys the hub against it. Readers who
are not rebuilding the image start at [Install kubectl](1_kubectl_install.md).

## References

- [Docker: `docker buildx build`](https://docs.docker.com/reference/cli/docker/buildx/build/)
- [Docker: multi-platform builds](https://docs.docker.com/build/building/multi-platform/)
- [NRP Documentation: Private Repos](https://nrp.ai/documentation/userdocs/development/private-repos/) — pull secrets in a namespace
- [Kubernetes: pull an image from a private registry](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)
- Supporting files in this repo: [image/Dockerfile](../image/Dockerfile), [image/requirements.txt](../image/requirements.txt), [scripts/build-push.sh](../scripts/build-push.sh), [configs/values.yaml](../configs/values.yaml)
