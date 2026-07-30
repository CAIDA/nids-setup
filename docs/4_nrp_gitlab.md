[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | **NRP GitLab** | [JupyterHub](5_nrp_jupyterhub.md)

---

# Building the Hub Image with NRP GitLab CI/CD

The JupyterHub you deploy next runs a **container image** — one combined image shared by all the NIDS assignment profiles. That image has to live somewhere the cluster can pull it from, and the natural home is NRP's own GitLab container registry. NRP GitLab doesn't just _store_ the image, though — it can **build** it too. This guide creates your NRP GitLab account, a **group**, and a project, then pushes the image sources there so GitLab's own runners build and publish the image for you. You never install Docker.

There is one wrinkle: these guides live on GitHub, so a single extra step wires the two hosts together. By now you've [configured `kubectl`](3_kubectl_config.md); after this you'll deploy [JupyterHub](5_nrp_jupyterhub.md), pointing it at the image the pipeline publishes here.

> **You can start this before your namespace is approved.** Building the image needs neither Docker nor `kubectl` — only the last section, [Letting the hub pull the image](#letting-the-hub-pull-the-image), touches your namespace. If your [namespace request](2_nrp_namespace.md) is still pending, work through Steps 1–5 now.

## Prerequisites

- An institutional identity that can log in via [CILogon](https://www.cilogon.org/) — the same one you used for the [NRP Portal](2_nrp_namespace.md).
- `git` installed locally, and a clone of this repo — you will add a second remote to it.
- An SSH key you can register with NRP GitLab (or a [personal access token](https://gitlab.nrp-nautilus.io/-/user_settings/personal_access_tokens) with the `write_repository` scope, if you must push over HTTPS).
- The image sources in this repo: [image/Dockerfile](../image/Dockerfile), [image/requirements.txt](../image/requirements.txt), and the pipeline definition [.gitlab-ci.yml](../.gitlab-ci.yml).

> **No Docker required.** The build runs on NRP's Kubernetes runners using **Kaniko**, which builds images inside an ordinary unprivileged pod. Nothing is installed on your machine. If you ever need to build by hand anyway, see [Building locally instead](#building-locally-instead).

## Step 1: Sign in to NRP GitLab

1. Go to [https://gitlab.nrp-nautilus.io](https://gitlab.nrp-nautilus.io).
2. Sign in with your institutional (CILogon) identity — the same provider you used for the NRP Portal. Your first sign-in provisions your GitLab account automatically.

Step 4 pushes over SSH, so the rest of this step gives GitLab a key to recognize you by.

### Generate an SSH key

Skip to [the next part](#register-the-public-key-with-gitlab) if you already have a key you want to reuse — `ls ~/.ssh/*.pub` lists what you have. Otherwise create one dedicated to NRP. The name `id_ed25519_nrp` below is an arbitrary label; it just has to match the `IdentityFile` you configure two sub-steps down:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_nrp -C "$USER@$(hostname) NRP GitLab"
```

Press Enter to accept the passphrase prompt empty, or set one — with a passphrase, add the key to your agent (`ssh-add ~/.ssh/id_ed25519_nrp`) so pushes don't prompt every time. This writes two files: the **private** key `~/.ssh/id_ed25519_nrp`, which never leaves your machine, and the **public** key `~/.ssh/id_ed25519_nrp.pub`, which is what you paste into GitLab.

### Register the public key with GitLab

Print the public key — note the `.pub`; pasting the private key is both a security mistake and rejected by GitLab:

```bash
cat ~/.ssh/id_ed25519_nrp.pub
```

Copy that single line (on macOS, `pbcopy < ~/.ssh/id_ed25519_nrp.pub` puts it on the clipboard; on Linux, `xclip -sel clip <`). In GitLab go to **User settings → SSH Keys → Add new key**, paste it into **Key**, and click **Add key**.

### Point SSH at the right host and key

NRP GitLab does **not** serve SSH on `gitlab.nrp-nautilus.io:22` — that port refuses connections. Git traffic goes to `gitlab-ssh.nrp-nautilus.io` on port **30622**, which is why every SSH URL below uses the `ssh://…:30622/…` form (the shorter `git@host:path` syntax cannot carry a port). Add a stanza to `~/.ssh/config` so you don't have to repeat the port and key on every command:

```
Host gitlab-ssh.nrp-nautilus.io
  Port 30622
  User git
  IdentityFile ~/.ssh/id_ed25519_nrp
  IdentitiesOnly yes
```

`IdentityFile` must name the **private** key (no `.pub`), and matching it to the file you generated above is what makes the whole thing work: SSH offers only default-named keys (`id_ed25519`, `id_rsa`, …) on its own, so a key named anything else — `id_ed25519_nrp` included — is silently never tried, and you get `Permission denied (publickey)` even though the key is sitting in your GitLab account. Confirm the whole path:

```bash
ssh -T gitlab-ssh.nrp-nautilus.io
```

A successful setup answers `Welcome to GitLab, @<your-username>!`.

## Step 2: Create Your GitLab Group

The registry path you push to is built from a GitLab **group** and **project** — `gitlab-registry.nrp-nautilus.io/<group>/<project>/…`. A **group** is a top-level namespace that owns one or more projects (repositories) along with their members. Its name becomes the group's URL path and must be **unique across the entire NRP GitLab instance** — not just within your account — so pick one that isn't already taken. Browse the existing groups at [https://gitlab.nrp-nautilus.io/explore/groups](https://gitlab.nrp-nautilus.io/explore/groups) to check what's already in use.

**These guides use the group `caida-nids` throughout.** Create it (or reuse it if you already own it):

1. Click **New group → Create group**.
2. Set **Group name** to `caida-nids` (GitLab derives the URL path `caida-nids` from it).
3. Choose the visibility, then click **Create group**.

## Step 3: Create a Project

Now create the project that will hold the image sources and the built image, **inside the `caida-nids` group**:

1. Click **New project → Create blank project**.
2. Under **Project URL**, select `caida-nids` as the namespace (group).
3. Set **Project name** to `nids-jupyterhub`.
4. Choose the visibility — this determines whether the hub can pull the image anonymously or needs credentials (see [Letting the hub pull the image](#letting-the-hub-pull-the-image)):
   - **Private** — visible only to project/group members. The cluster needs a deploy token + `imagePullSecrets` to pull. Safest default if the image or its dependency list shouldn't be public.
   - **Internal** — visible to anyone signed in to NRP GitLab, but pulls still require credentials, same as **Private**. Rarely useful here since it doesn't simplify the hub's pull.
   - **Public** — anyone can view the project and pull the image with no credentials. Simplest option for the hub (no deploy token/pull secret setup), at the cost of exposing the Dockerfile/image contents publicly.
5. **Clear the "Initialize repository with a README" checkbox.** It is ticked by default, and the initial commit it creates will make Step 4's push fail.
6. Click **Create project**.

The project's path is now `caida-nids/nids-jupyterhub`. CI exposes that path as `$CI_REGISTRY_IMAGE`, so the image the pipeline publishes lands at `gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub`.

## Step 4: Add the GitLab Project as a Second Git Remote

NRP GitLab CI/CD only runs pipelines for repositories hosted **in NRP GitLab**, and this repo lives on GitHub. So add the new project as a second remote and push to it. `origin` keeps pointing at GitHub; `nrp` is the copy that builds.

```bash
git remote add nrp ssh://git@gitlab-ssh.nrp-nautilus.io:30622/caida-nids/nids-jupyterhub.git
git remote -v
git push nrp main
```

That push carries [.gitlab-ci.yml](../.gitlab-ci.yml) along with the image sources, which is all it takes to trigger the first build.

> **"Updates were rejected."** You left **Initialize repository with a README** ticked in Step 3, so GitLab has a commit your history doesn't descend from. Either delete and recreate the project empty, or run `git push --force nrp main` — the GitLab copy is a mirror of your history, not a separate line of work.

> **The two remotes do not sync themselves.** After every image change you need `git push origin main` _and_ `git push nrp main`. To fan out from a single `git push`, add the second URL as an extra push target: `git remote set-url --add --push origin git@github.com:CAIDA/nids-setup.git` followed by `git remote set-url --add --push origin ssh://git@gitlab-ssh.nrp-nautilus.io:30622/caida-nids/nids-jupyterhub.git`.

> **Mirroring isn't an option.** GitLab can pull-mirror an external repo, but that is a Premium feature and NRP GitLab doesn't offer it — a second remote is the supported path.

## Step 5: Watch the Pipeline

The push in Step 4 already started a build.

1. Go to **Build → Pipelines** in your project.
2. Click the running pipeline, then the `build-and-push-job` to stream its log.
3. To rebuild by hand later, use **Build → Pipelines → Run pipeline** on branch `main`.

**Expect the first build to take tens of minutes.** Kaniko pulls and unpacks a multi-gigabyte Spark base image, compiles the Python dependencies, and downloads the Spark S3A JARs before pushing the result. The log's landmarks, in order:

```
Retrieving image manifest quay.io/jupyter/all-spark-notebook@sha256:...
Building stage 'quay.io/jupyter/all-spark-notebook@sha256:...'
... pip install output ...
... two curl fetches for the hadoop-aws and aws-sdk JARs ...
Taking snapshot of full filesystem...
Pushing image to gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub:latest
Job succeeded
```

If **Build → Pipelines** isn't there at all, check **Settings → General → Visibility** and confirm **CI/CD** and **Container Registry** are enabled, then check that **Settings → CI/CD → Runners** lists available instance runners.

## Step 6: Verify the Image

First in GitLab: **Deploy → Container Registry** should list `nids-hub` with tags `latest` and the commit's short SHA, plus a `nids-hub/cache` repository holding Kaniko's layer cache.

Then from the cluster. This is the Docker-free equivalent of a local `docker run`, and it proves the pull path, the CPU architecture, and the dependency set in one shot:

```bash
kubectl run nids-hub-smoke -n <YOUR_NAMESPACE> --rm -it --restart=Never \
  --image=gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub:latest \
  --command -- python -c "import pyspark, dpkt, pytricia, pybgpkit_parser, pelicanfs, neo4j; print('ok')"
```

> `ImagePullBackOff` means the cluster can't pull the image — either the project is private and has no pull secret yet (see [Letting the hub pull the image](#letting-the-hub-pull-the-image)), or the tag isn't published. `exec format error` means the image was built for the wrong CPU architecture (see [If the build fails](#if-the-build-fails)).

## How the pipeline works

The pipeline lives in [.gitlab-ci.yml](../.gitlab-ci.yml) at the repo root:

```yaml
image: ghcr.io/osscontainertools/kaniko:debug

stages:
  - build-and-push

workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "web"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      changes:
        - image/**/*
        - .gitlab-ci.yml
    - when: never

build-and-push-job:
  stage: build-and-push
  interruptible: true
  timeout: 3h
  variables:
    GODEBUG: "http2client=0"
    IMAGE: $CI_REGISTRY_IMAGE/nids-hub
  script:
    - echo "{\"auths\":{\"$CI_REGISTRY\":{\"username\":\"$CI_REGISTRY_USER\",\"password\":\"$CI_REGISTRY_PASSWORD\"}}}" > /kaniko/.docker/config.json
    - >-
      /kaniko/executor
      --context $CI_PROJECT_DIR/image
      --dockerfile $CI_PROJECT_DIR/image/Dockerfile
      --destination $IMAGE:$CI_COMMIT_SHORT_SHA
      --destination $IMAGE:latest
      --cache=true
      --cache-repo $IMAGE/cache
      --compressed-caching=false
      --push-retry=10
```

The parts worth knowing:

- **`$CI_REGISTRY`, `$CI_REGISTRY_USER`, `$CI_REGISTRY_PASSWORD`** are injected by GitLab. No credentials are committed anywhere.
- **`$CI_REGISTRY_IMAGE`** expands to `gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub`, so `$IMAGE` lands exactly on the `singleuser.image.name` in [configs/values.yaml](../configs/values.yaml).
- **`GODEBUG: "http2client=0"`** is required, not cosmetic — without it Kaniko's push to GitLab is pathologically slow. NRP documents this workaround.
- **Two destination tags:** `latest` for the hub to track, and the immutable `<short-sha>` so you can pin and roll back.
- **`--context $CI_PROJECT_DIR/image`** because the Dockerfile is in `image/`, not at the repo root.
- **`--cache-repo`** is where the `nids-hub/cache` repository in the registry UI comes from.
- **`--compressed-caching=false`** trades build time for much lower memory use; it's the documented fix for Kaniko running out of memory on large, many-layered base images.
- **The `workflow:` rules** mean a docs-only commit creates no pipeline at all — a full rebuild is expensive on a shared cluster. It sits in `workflow:` rather than the job so those commits produce _no_ pipeline, instead of an empty one that errors.

> **Docker builder instead.** NRP also documents a `docker:dind` variant using `tags: [docker]` and `docker buildx build --push --provenance=false --platform linux/amd64`. Prefer it only when byte-for-byte Docker compatibility or a genuine multiarch manifest matters more than avoiding NRP's single shared Docker build server — Kaniko runs on the ordinary runners, of which there are many.

## What's in the image

All profiles share **one combined image** — the dependency sets are additive, and only the DNS assignment needs Spark. Python dependencies come from [image/requirements.txt](../image/requirements.txt), the union of the assignments' imports.

The image also pre-stages the DNS assignment's Spark S3A JARs (`hadoop-aws:3.4.0`, `software.amazon.awssdk:bundle:2.24.6`) so a Spark session doesn't depend on Maven Central egress at startup — see [image/Dockerfile](../image/Dockerfile). The base image is pinned by digest rather than `:latest`, because a moving base invalidates the whole build cache.

> Split the DNS/Spark image off from a plain BGP+telescope image **only** if the combined image becomes unwieldy or a real version-pin conflict appears.

## Rebuilding and versioning the image

Edit anything under `image/`, commit, and push to both remotes — the `changes:` rule matches and the pipeline rebuilds:

```bash
git push origin main
git push nrp main
```

> **Pin the tag, not `latest`.** `latest` is mutable, and Kubernetes defaults to `imagePullPolicy: IfNotPresent`, so a node that already cached `latest` will keep serving the _old_ image. When you need a rollout you can prove happened, set `singleuser.image.tag` in [configs/values.yaml](../configs/values.yaml) to the build's short SHA (shown against the tag in **Deploy → Container Registry**).

Each build adds a SHA tag plus cache layers, all multi-gigabyte, and NRP does **not** back up container images. Enable **Settings → Packages and registries → Clean up image tags** to keep `latest` and the most recent few SHAs.

## Letting the hub pull the image

If you made the project **private**, the cluster needs credentials to pull it. Either make the project (or just its registry) **public**, or create a **deploy token** with the `read_registry` scope under **Settings → Repository → Deploy Tokens**, then store it as a pull secret in your namespace:

```bash
kubectl create secret docker-registry regcred -n <YOUR_NAMESPACE> \
  --docker-server=gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub \
  --docker-username=gitlab+deploy-token-<TOKEN_ID> \
  --docker-password=<DEPLOY_TOKEN>
```

Then uncomment the `imagePullSecrets` stanza in [configs/values.yaml](../configs/values.yaml). Use the chart's **top-level** `imagePullSecrets`, not `singleuser.image.pullSecrets` — the hub, the user pods, _and_ the chart's image puller all need the credential.

> If pulls still fail, recreate the secret with the bare host `gitlab-registry.nrp-nautilus.io` as `--docker-server`. See [Private Repos](https://nrp.ai/documentation/userdocs/development/private-repos/).

## If the build fails

The first pipeline run is effectively the image's acceptance test — it has not been run end to end yet. Symptoms and fixes:

| Symptom                                          | Cause                                                                      | Fix                                                                                                                                               |
| ------------------------------------------------ | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Job `OOMKilled`                                  | Kaniko holds layer tars in memory; the base is large and many-layered      | `--compressed-caching=false` is already set; escalate to `--single-snapshot`, then `--snapshot-mode=redo`, then uncomment `KUBERNETES_MEMORY_*`   |
| `no space left on device`, or the job is evicted | Extracted base + compiled deps + JARs + snapshot tars need well over 10 GB | Uncomment `KUBERNETES_EPHEMERAL_STORAGE_*`; if the runner forbids overrides, use the Docker builder or [build locally](#building-locally-instead) |
| Job times out                                    | GitLab's default project timeout is 1 hour; a cold build can exceed it     | `timeout: 3h` is set in the job; also raise **Settings → CI/CD → General pipelines → Timeout** (the runner's own maximum still caps it)           |
| Push crawls                                      | Kaniko/GitLab HTTP/2 issue on a multi-GB image                             | Confirm `GODEBUG: "http2client=0"` and `--push-retry=10`                                                                                          |
| `error: command 'gcc' failed`                    | `pytricia` is source-only with a C extension                               | Add `build-essential` in a root `RUN apt-get` layer before the pip install                                                                        |
| `exec format error` at pod start                 | Image built for the wrong CPU architecture                                 | Kaniko builds for its runner's architecture; pin `nodeSelector` to `amd64` in `values.yaml`, or use the buildx multiarch variant                  |
| Pipeline never ran                               | The `changes:` gate                                                        | Expected for docs-only commits — use **Run pipeline**                                                                                             |
| `denied: access forbidden`                       | Pushed to the wrong project path                                           | Check `git remote -v` against the project's registry path                                                                                         |
| Every rebuild is slow                            | Base image moved, invalidating the layer cache                             | The base is digest-pinned in [image/Dockerfile](../image/Dockerfile); bump it deliberately                                                        |

> **Open item:** `pyspark` is listed in [image/requirements.txt](../image/requirements.txt), but the base image already ships Spark — pip installs a second, possibly version-skewed copy. It likely wants removing, pending a real Spark session against the DNS notebook to confirm.

## Building locally instead

If CI is unavailable you can still build by hand, with [Docker](https://docs.docker.com/get-docker/) installed locally. Authenticate first — if you have **Two-Factor Authentication** enabled, use a [personal access token](https://gitlab.nrp-nautilus.io/-/user_settings/personal_access_tokens) with the `write_registry` scope as the password:

```bash
docker login gitlab-registry.nrp-nautilus.io
docker build --platform linux/amd64 \
  -t gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub:latest image/
docker push gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub:latest
```

> **`--platform linux/amd64` is not optional** on Apple Silicon or any other ARM machine. NRP's nodes are predominantly x86, and an arm64 image will fail at pod start with `exec format error` — a failure that shows up only when a student tries to spawn a server.

## Next

With the image published to your registry, continue to [JupyterHub](5_nrp_jupyterhub.md) to deploy the hub, using this image path — and the short-SHA tag if you pinned it — for `singleuser.image` in [configs/values.yaml](../configs/values.yaml).

## References

- [NRP Documentation: Building in GitLab](https://nrp.ai/documentation/userdocs/development/gitlab/)
- [NRP Documentation: Private Repos](https://nrp.ai/documentation/userdocs/development/private-repos/)
- [NRP Documentation: K8s GitLab Integration](https://nrp.ai/documentation/userdocs/development/k8s-integration/)
- [Kaniko](https://github.com/osscontainertools/kaniko) — the builder the pipeline uses
- [GitLab: predefined CI/CD variables](https://docs.gitlab.com/ci/variables/predefined_variables/)
- [GitLab: reduce container registry storage](https://docs.gitlab.com/user/packages/container_registry/reduce_container_registry_storage/)
- Supporting files in this repo: [.gitlab-ci.yml](../.gitlab-ci.yml), [image/Dockerfile](../image/Dockerfile), [image/requirements.txt](../image/requirements.txt), [configs/values.yaml](../configs/values.yaml)

---

[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | **NRP GitLab** | [JupyterHub](5_nrp_jupyterhub.md)
