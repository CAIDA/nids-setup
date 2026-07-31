**Install kubectl** | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [JupyterHub](4_nrp_jupyterhub.md) | [Verify](5_verify_hub.md)

---

# Installing `kubectl` and the `kubelogin` Plugin

> **Path: your own hub — skippable on the community hub.** `kubectl` is only needed to *deploy and
> operate* a JupyterHub of your own. **No assignment ever needs it**: every dataset is read from
> inside the notebook server over HTTP, S3A, or Postgres, never through Kubernetes. If you are using
> the [community hub](../README.md#start-here-whose-hub-will-you-use), skip this guide and start at
> [NRP & Namespace](2_nrp_namespace.md) — install `kubectl` only if you want to inspect your
> namespace from the command line.

This guide covers installing the `kubectl` command-line tool and the `kubelogin` OIDC plugin on your local machine. Neither step needs an NRP account or namespace — it's just local tooling. It is the first step of the own-hub path; next request a [namespace](2_nrp_namespace.md), then [configure `kubectl`](3_kubectl_config.md) to talk to NRP.

## Prerequisites

- A local shell with `curl`, `unzip`, and `jq` available (used by the `kubelogin` install snippet below).

## Step 1: Install `kubectl`

Install the Kubernetes command-line tool for your OS following the [official instructions](https://kubernetes.io/docs/tasks/tools/).

Verify it's installed:

```bash
kubectl version --client
```

## Step 2: Install the `kubelogin` Plugin

NRP uses OIDC (CILogon) authentication, so the `kubelogin` plugin is **required**. On Linux/macOS:

```bash
OS_ARCHITECTURE="$(uname -m)"
OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
KUBELOGIN_VERSION="$(curl -fsSL "https://api.github.com/repos/int128/kubelogin/releases/latest" | jq -r '.tag_name')"
curl -o kubelogin.zip -fSL "https://github.com/int128/kubelogin/releases/download/${KUBELOGIN_VERSION}/kubelogin_${OS_NAME}_${OS_ARCHITECTURE}.zip"
unzip kubelogin.zip kubelogin
chmod +x ./kubelogin
sudo mv ./kubelogin /usr/local/bin/kubectl-oidc_login
```

See the [kubelogin setup docs](https://github.com/int128/kubelogin?tab=readme-ov-file#setup) for other platforms and install methods.

## Next

With `kubectl` installed, continue to [NRP & Namespace](2_nrp_namespace.md) to get access to NRP and request a namespace.

## References

- [Install kubectl](https://kubernetes.io/docs/tasks/tools/)
- [kubelogin (OIDC plugin)](https://github.com/int128/kubelogin)

---

**Install kubectl** | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [JupyterHub](4_nrp_jupyterhub.md) | [Verify](5_verify_hub.md)
