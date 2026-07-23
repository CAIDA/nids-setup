[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | **NRP GitLab** | [JupyterHub](5_nrp_jupyterhub.md)

---

# Building and Pushing the Container Image to NRP GitLab

The JupyterHub you deploy next runs a **container image** — one combined image shared by all three NIDS assignment profiles. That image has to live somewhere the cluster can pull it from, and the natural home is NRP's own GitLab container registry. This guide creates your NRP GitLab account, a **group**, and a project to hold the image, then builds and pushes it. You'll do this once (and rebuild whenever the image changes).

By now you've [configured `kubectl`](3_kubectl_config.md); after this you'll deploy [JupyterHub](5_nrp_jupyterhub.md), pointing it at the image you push here.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed locally (to build and push the image).
- An institutional identity that can log in via [CILogon](https://www.cilogon.org/) — the same one you used for the [NRP Portal](2_nrp_namespace.md).
- The image sources in this repo: [image/Dockerfile](../image/Dockerfile) and [image/requirements.txt](../image/requirements.txt).

## Step 1: Sign in to NRP GitLab

1. Go to [https://gitlab.nrp-nautilus.io](https://gitlab.nrp-nautilus.io).
2. Sign in with your institutional (CILogon) identity — the same provider you used for the NRP Portal. Your first sign-in provisions your GitLab account automatically.

## Step 2: Create Your GitLab Group

The registry path you push to is built from a GitLab **group** and **project** — `gitlab-registry.nrp-nautilus.io/<group>/<project>/…`. A **group** is a top-level namespace that owns one or more projects (repositories) along with their members. Its name becomes the group's URL path and must be **unique across the entire NRP GitLab instance** — not just within your account — so pick one that isn't already taken. Browse the existing groups at [https://gitlab.nrp-nautilus.io/explore/groups](https://gitlab.nrp-nautilus.io/explore/groups) to check what's already in use.

**These guides use the group `caida-nids` throughout.** Create it (or reuse it if you already own it):

1. Click **New group → Create group**.
2. Set **Group name** to `caida-nids` (GitLab derives the URL path `caida-nids` from it).
3. Choose the visibility, then click **Create group**.

## Step 3: Create a Project

Now create the project that will hold the hub image, **inside the `caida-nids` group**:

1. Click **New project → Create blank project**.
2. Under **Project URL**, select `caida-nids` as the namespace (group).
3. Set **Project name** to `nids-jupyterhub`.
4. Choose the visibility (see the note under Step 5 about how visibility affects the hub pulling the image).
5. Click **Create project**.

The project's path is now `caida-nids/nids-jupyterhub`, so the image you build below lives at `gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub`.

## Step 4: Log in to the Container Registry

Authenticate Docker to the registry before pushing:

```bash
docker login gitlab-registry.nrp-nautilus.io
```

Enter your GitLab username and password. If you have **Two-Factor Authentication** enabled, use a [personal access token](https://gitlab.nrp-nautilus.io/-/user_settings/personal_access_tokens) (with the `write_registry` scope) as the password instead. The exact registry address for your project is also shown in the GitLab UI under **Deploy → Container Registry**.

## Step 5: Build and Push the Image

All three profiles share **one combined image** — the dependency sets are additive, and only the DNS assignment needs Spark. Build from [image/Dockerfile](../image/Dockerfile) (Python deps in [image/requirements.txt](../image/requirements.txt)) and push to your project's registry:

```bash
docker build -t gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub:latest image/
docker push  gitlab-registry.nrp-nautilus.io/caida-nids/nids-jupyterhub/nids-hub:latest
```

This is the exact path you set as `singleuser.image.name` in [configs/values.yaml](../configs/values.yaml) in the [JupyterHub](5_nrp_jupyterhub.md) step.

The image pre-stages the DNS assignment's Spark S3A JARs (`hadoop-aws:3.4.0`, `software.amazon.awssdk:bundle:2.24.6`) so a Spark session doesn't depend on Maven Central egress at startup — see [image/Dockerfile](../image/Dockerfile). Ideally automate the build/push via [NRP GitLab CI/CD](https://nrp.ai/documentation/userdocs/development/gitlab-ci/).

> Split the DNS/Spark image off from a plain BGP+telescope image **only** if the combined image becomes unwieldy or a real version-pin conflict appears.

> **Letting the hub pull the image.** If you made the project **private**, the cluster needs credentials to pull it: either make the project (or just its registry) **public**, or create a **deploy token** with the `read_registry` scope (**Settings → Repository → Deploy Tokens**), store it as a `regcred` pull secret in your namespace, and reference it via `imagePullSecrets` — see [Private Repos](https://nrp.ai/documentation/userdocs/development/private-repos/).

## Next

With the image built and pushed, continue to [JupyterHub](5_nrp_jupyterhub.md) to deploy the hub, using this image path for `singleuser.image` in [configs/values.yaml](../configs/values.yaml).

## References

- [NRP Documentation: Building in GitLab](https://nrp.ai/documentation/userdocs/development/gitlab/)
- [NRP Documentation: Private Repos](https://nrp.ai/documentation/userdocs/development/private-repos/)
- [NRP Documentation: GitLab CI/CD](https://nrp.ai/documentation/userdocs/development/gitlab-ci/)
- Supporting files in this repo: [image/Dockerfile](../image/Dockerfile), [image/requirements.txt](../image/requirements.txt), [configs/values.yaml](../configs/values.yaml)

---

[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | **NRP GitLab** | [JupyterHub](5_nrp_jupyterhub.md)
