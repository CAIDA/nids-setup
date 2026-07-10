**NRP & Namespace** | [kubectl](kubectl.md) | [JupyterHub](JupyterHub.md)

---

# Getting Access to NRP and Requesting a Namespace

This guide walks through getting onboarded to the National Research Platform (NRP) Nautilus Kubernetes cluster and requesting your own namespace. It is the first step; next set up [kubectl](kubectl.md), then deploy [JupyterHub](JupyterHub.md).

## What is NRP / Nautilus?

The [National Research Platform (NRP)](https://nrp.ai/) operates **Nautilus**, a distributed Kubernetes cluster shared across research institutions. Work is isolated per project/lab into **namespaces** — logical partitions with their own compute and storage quotas.

## Prerequisites

- An institutional identity that can log in via [CILogon](https://www.cilogon.org/) (university/InCommon affiliation, or a GitHub account, depending on what your institution supports).
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/#kubectl) installed locally.

## Step 1: Log into the NRP Portal

1. Go to the [NRP Portal](https://portal.nrp-nautilus.io).
2. Sign in with CILogon, selecting your institution (or GitHub) as the identity provider.

## Step 2: Set Up `kubectl` Access

Install and configure `kubectl` (plus the required `kubelogin` OIDC plugin) so it can talk to Nautilus. See the dedicated guide: [kubectl.md](kubectl.md).

## Step 3: Request a Namespace

If you don't already have an active namespace or admin rights to create one:

1. In the [NRP Portal](https://nrp.ai/namespaces), find the namespace request form.
2. Provide:
   - A namespace name (usually tied to your project or lab).
   - Your sponsoring PI/group.
   - A brief justification and the resource quota you expect to need (CPU/GPU/memory/storage).
3. Submit the request. New namespaces typically require admin or PI approval before they're provisioned — this can take a few days.

## Step 4: Confirm Namespace Access

Once approved, switch your local `kubectl` context to the new namespace and confirm access:

```bash
kubectl config set-context --current --namespace=<YOUR_NAMESPACE>
kubectl get pods -n <YOUR_NAMESPACE>
```

An empty pod list (no errors) confirms you have access.

## Step 5 (Optional): Add Teammates to the Namespace

If others need access to the same namespace, use the namespace membership management options in the [NRP Portal](https://nrp.ai/namespaces) to add them.

## Next

Once your namespace is active, continue to [kubectl.md](kubectl.md) to set up `kubectl`, then [JupyterHub.md](JupyterHub.md) to deploy your own JupyterHub into it.

## References

- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [NRP Portal](https://portal.nrp-nautilus.io)
- [NRP Namespaces](https://nrp.ai/namespaces)
- [CILogon](https://www.cilogon.org/)
