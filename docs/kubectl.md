[NRP & Namespace](NRP_Namespace.md) | **kubectl** | [JupyterHub](JupyterHub.md)

---

# Setting Up `kubectl` for Your NRP Namespace

This guide covers installing and configuring `kubectl` so it can talk to the NRP Nautilus cluster and default to your namespace. You'll need this before deploying anything (see [JupyterHub](JupyterHub.md)).

## Prerequisites

- An NRP account — you can log into the [NRP Portal](https://portal.nrp-nautilus.io) via CILogon (see [NRP & Namespace](NRP_Namespace.md)).
- A namespace you have access to (its name is referred to below as `<YOUR_NAMESPACE>`).

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

## Step 3: Download and Install Your Config File

Log into the [NRP Portal](https://portal.nrp-nautilus.io) first, then download your kubeconfig and save it as `~/.kube/config`:

```bash
mkdir -p ~/.kube
curl -o ~/.kube/config -fSL "https://nrp.ai/config"
```

> If you already have a `~/.kube/config` for other clusters, back it up first — this overwrites it. To merge instead, download to a separate file and set `KUBECONFIG` to include both.

## Step 4: Select the Nautilus Context

```bash
kubectl config get-contexts
kubectl config use-context nautilus
```

## Step 5: Set Your Default Namespace

So you don't have to pass `-n <YOUR_NAMESPACE>` on every command:

```bash
kubectl config set contexts.nautilus.namespace <YOUR_NAMESPACE>
```

## Step 6: Verify Access

```bash
kubectl get pods -n <YOUR_NAMESPACE>
```

The first command will open a browser window for CILogon login. After authenticating, an empty pod list (with no errors) confirms `kubectl` is working against your namespace.

## Refreshing an Expired Token

If authentication starts failing, clear the cached OIDC token and re-run any `kubectl` command to re-authenticate:

```bash
kubectl oidc-login clean
```

## References

- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [Install kubectl](https://kubernetes.io/docs/tasks/tools/)
- [kubelogin (OIDC plugin)](https://github.com/int128/kubelogin)
