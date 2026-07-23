**Install kubectl** | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [NRP GitLab](4_nrp_gitlab.md) | [JupyterHub](5_nrp_jupyterhub.md)

---

# Installing `kubectl` and the `kubelogin` Plugin

This guide covers installing the `kubectl` command-line tool and the `kubelogin` OIDC plugin on your local machine. Neither step needs an NRP account or namespace — it's just local tooling. It is the first step; next request a [namespace](2_nrp_namespace.md), then [configure `kubectl`](3_kubectl_config.md) to talk to NRP.

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

**Install kubectl** | [NRP & Namespace](2_nrp_namespace.md) | [Configure kubectl](3_kubectl_config.md) | [NRP GitLab](4_nrp_gitlab.md) | [JupyterHub](5_nrp_jupyterhub.md)
