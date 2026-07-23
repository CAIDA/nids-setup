[Install kubectl](1_kubectl_install.md) | **NRP & Namespace** | [Configure kubectl](3_kubectl_config.md) | [NRP GitLab](4_nrp_gitlab.md) | [JupyterHub](5_nrp_jupyterhub.md)

---

# Getting Access to NRP and Requesting a Namespace

This guide walks through getting onboarded to the National Research Platform (NRP) Nautilus Kubernetes cluster and requesting your own namespace. By now you've [installed `kubectl`](1_kubectl_install.md); next you'll [configure `kubectl`](3_kubectl_config.md) to talk to NRP, then deploy [JupyterHub](5_nrp_jupyterhub.md).

## What is NRP / Nautilus?

The [National Research Platform (NRP)](https://nrp.ai/) operates **Nautilus**, a distributed Kubernetes cluster shared across research institutions. Work is isolated per project/lab into **namespaces** — logical partitions with their own compute and storage quotas.

## Prerequisites

- An institutional identity that can log in via [CILogon](https://www.cilogon.org/) (university/InCommon affiliation, or a GitHub account, depending on what your institution supports).
- [`kubectl`](1_kubectl_install.md) installed locally.

## Step 1: Log into the NRP Portal

1. Go to the [NRP Portal](https://portal.nrp-nautilus.io).
2. Sign in with CILogon, selecting your institution (or GitHub) as the identity provider.

## Step 2: Request a Namespace

If you don't already have an active namespace or admin rights to create one:

1. In the [NRP Portal](https://nrp.ai/namespaces), find the namespace request form.
2. Provide:
   - A namespace name (usually tied to your project or lab).
   - Your sponsoring PI/group.
   - A brief justification and the resource quota you expect to need (CPU/GPU/memory/storage).
3. Submit the request. New namespaces typically require admin or PI approval before they're provisioned — this can take a few days.

## Step 3 (Optional): Add Teammates to the Namespace

If others need access to the same namespace, use the namespace membership management options in the [NRP Portal](https://nrp.ai/namespaces) to add them.

## Your Hub's Hostname (`HUB_HOST`)

The namespace request doesn't ask for a hostname, but the JupyterHub you deploy later needs one — and it's worth settling now. NRP runs a wildcard DNS record: `*.nrp-nautilus.io` resolves to the cluster's ingress. You expose a service by *claiming a subdomain* under it — you pick the label `HUB_HOST`, and your hub lives at `https://<HUB_HOST>.nrp-nautilus.io`. You can choose almost any label ([NRP: Exposing HTTP](https://nrp.ai/documentation/userdocs/running/ingress/)), but a given host can only be claimed by one ingress at a time, so it must be unique across all of NRP — not just within your namespace. TLS is handled for you: cert-manager issues a Let's Encrypt certificate for the host automatically.

`HUB_HOST` then threads through the entire JupyterHub setup — the CILogon OAuth **callback URL** (`https://<HUB_HOST>.nrp-nautilus.io/hub/oauth_callback`), the ingress `hosts`, and the TLS secret name all embed it (see [JupyterHub](5_nrp_jupyterhub.md) and [configs/values.yaml](../configs/values.yaml)). Registering the CILogon app against the wrong host is the most common setup snag, so pin the name before you register anything.

> **Recommendation.** Derive `HUB_HOST` from your namespace so it's unique and self-documenting — e.g. `<your-namespace>-jhub`, giving `https://<your-namespace>-jhub.nrp-nautilus.io`. Keep it lowercase and DNS-safe (letters, digits, hyphens), short, and stable: changing it later means re-issuing the CILogon callback and re-deploying. During NRP's migration from Ingress to the Gateway API, hosts may also be reachable on ports **50080/50443** (e.g. `https://<HUB_HOST>.nrp-nautilus.io:50443`).

## Next

Once your namespace is active, continue to [Configure kubectl](3_kubectl_config.md) to point `kubectl` at NRP and your namespace — that guide also confirms your namespace access — then [JupyterHub](5_nrp_jupyterhub.md) to deploy your own JupyterHub into it.

## References

- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [NRP Documentation: Exposing HTTP (Ingress)](https://nrp.ai/documentation/userdocs/running/ingress/)
- [NRP Documentation: Gateway API](https://nrp.ai/documentation/userdocs/running/gateway/)
- [NRP Portal](https://portal.nrp-nautilus.io)
- [NRP Namespaces](https://nrp.ai/namespaces)
- [CILogon](https://www.cilogon.org/)

---

[Install kubectl](1_kubectl_install.md) | **NRP & Namespace** | [Configure kubectl](3_kubectl_config.md) | [NRP GitLab](4_nrp_gitlab.md) | [JupyterHub](5_nrp_jupyterhub.md)
