# Getting Access to NRP and Requesting a Namespace

This guide walks through getting onboarded to the National Research Platform (NRP) Nautilus Kubernetes cluster and requesting your own namespace. Completing this is a prerequisite for [JupyterHub.md](JupyterHub.md).

## What is NRP / Nautilus?

The [National Research Platform (NRP)](https://nrp.ai/) operates **Nautilus**, a distributed Kubernetes cluster shared across research institutions. Work is isolated per project/lab into **namespaces** — logical partitions with their own compute and storage quotas.

## Prerequisites

- An institutional identity that can log in via [CILogon](https://www.cilogon.org/) (university/InCommon affiliation, or a GitHub account, depending on what your institution supports).
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/#kubectl) installed locally.

## Step 1: Log into the NRP Portal

1. Go to the [NRP Portal](https://portal.nrp-nautilus.io).
2. Sign in with CILogon, selecting your institution (or GitHub) as the identity provider.

## Step 2: Set Up `kubectl` Access

1. From the portal, download your kubeconfig file.
2. Merge or point `kubectl` at it, e.g.:

   ```bash
   export KUBECONFIG=~/Downloads/<your-downloaded-config>.yaml
   ```

3. Verify connectivity:

   ```bash
   kubectl get nodes
   kubectl config get-contexts
   ```

See the [NRP Getting Started guide](https://nrp.ai/documentation/userdocs/start/getting-started/) for the full reference.

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

Once your namespace is active, continue to [JupyterHub.md](JupyterHub.md) to deploy your own JupyterHub into it.
