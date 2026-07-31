[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | **Configure kubectl** | [JupyterHub](4_nrp_jupyterhub.md) | [Verify](5_verify_hub.md)

---

# Configuring `kubectl` for Your NRP Namespace

> **Path: your own hub — skippable on the community hub.** You never run `kubectl` against your
> namespace on the [community hub](../README.md#start-here-whose-hub-will-you-use); skip to
> [Verify](5_verify_hub.md). The one reason to do it anyway: Step 4 below is the quickest
> confirmation that your namespace is actually live.

Now that `kubectl` is [installed](1_kubectl_install.md) and you have an [active namespace](2_nrp_namespace.md), this guide wires `kubectl` up to the NRP Nautilus cluster and defaults it to your namespace. You'll need this before deploying anything (see [JupyterHub](4_nrp_jupyterhub.md)).

## Prerequisites

- [`kubectl` and the `kubelogin` plugin installed](1_kubectl_install.md).
- An [active NRP namespace](2_nrp_namespace.md) you have access to (its name is referred to below as `<YOUR_NAMESPACE>`).

## Step 1: Download and Install Your Config File

Log into the [NRP Portal](https://portal.nrp-nautilus.io) first, then download your kubeconfig and save it as `~/.kube/config`:

```bash
mkdir -p ~/.kube
curl -o ~/.kube/config -fSL "https://nrp.ai/config"
```

> If you already have a `~/.kube/config` for other clusters, back it up first — this overwrites it. To merge instead, download to a separate file and set `KUBECONFIG` to include both.

## Step 2: Select the Nautilus Context

```bash
kubectl config get-contexts
kubectl config use-context nautilus
```

## Step 3: Set Your Default Namespace

So you don't have to pass `-n <YOUR_NAMESPACE>` on every command:

```bash
kubectl config set contexts.nautilus.namespace <YOUR_NAMESPACE>
```

## Step 4: Verify Access

```bash
kubectl get pods -n <YOUR_NAMESPACE>
```

This command will open a browser window for CILogon login. After authenticating, an empty pod list (with no errors) confirms `kubectl` is working against your namespace.

## Refreshing an Expired Token

If authentication starts failing, clear the cached OIDC token and re-run any `kubectl` command to re-authenticate:

```bash
kubectl oidc-login clean
```

## Next

With `kubectl` talking to your namespace, continue to [JupyterHub](4_nrp_jupyterhub.md) to deploy your own JupyterHub into it.

## References

- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [kubelogin (OIDC plugin)](https://github.com/int128/kubelogin)

---

[Install kubectl](1_kubectl_install.md) | [NRP & Namespace](2_nrp_namespace.md) | **Configure kubectl** | [JupyterHub](4_nrp_jupyterhub.md) | [Verify](5_verify_hub.md)
