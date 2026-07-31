[Install kubectl](1_kubectl_install.md) | **NRP & Namespace** | [Configure kubectl](3_kubectl_config.md) | [JupyterHub](4_nrp_jupyterhub.md) | [Verify](5_verify_hub.md)

---

# Getting Access to NRP and Requesting a Namespace

> **Path: split — read the first half either way.**
> **Steps 1–3 are for everyone.** You need an NRP identity and a namespace whether you use the
> [community hub](../README.md#start-here-whose-hub-will-you-use) or deploy your own, and approval
> can take days — start here.
> **Steps 4–5 (`HUB_HOST` and the CILogon OAuth application) are for your own hub only.** The
> community hub already has a hostname and its own OAuth registration; skip both sections and
> continue to [Verify](5_verify_hub.md).

This guide walks through getting onboarded to the National Research Platform (NRP) Nautilus Kubernetes cluster and requesting your own namespace. On the own-hub path you have already [installed `kubectl`](1_kubectl_install.md); next you'll [configure `kubectl`](3_kubectl_config.md) to talk to NRP, then deploy [JupyterHub](4_nrp_jupyterhub.md).

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

---

_Steps 1–3 above are the whole guide if you are using the community hub — continue to
[Verify](5_verify_hub.md). Steps 4 and 5 below set up a hub of your own._

---

## Step 4: Your Hub's Hostname (`HUB_HOST`)

**Your own hub only.** The namespace request doesn't ask for a hostname, but the JupyterHub you deploy later needs one — and it's worth settling now. NRP runs a wildcard DNS record: `*.nrp-nautilus.io` resolves to the cluster's ingress. You expose a service by _claiming a subdomain_ under it — you pick the label `HUB_HOST`, and your hub lives at `https://<HUB_HOST>.nrp-nautilus.io`. You can choose almost any label ([NRP: Exposing HTTP](https://nrp.ai/documentation/userdocs/running/ingress/)), but a given host can only be claimed by one ingress at a time, so it must be unique across all of NRP — not just within your namespace. TLS is handled for you: cert-manager issues a Let's Encrypt certificate for the host automatically.

`HUB_HOST` then threads through the entire JupyterHub setup — the CILogon OAuth **callback URL** (`https://<HUB_HOST>.nrp-nautilus.io/hub/oauth_callback`), the ingress `hosts`, and the TLS secret name all embed it (see [JupyterHub](4_nrp_jupyterhub.md) and [configs/values.yaml](../configs/values.yaml)). Registering the CILogon app against the wrong host is the most common setup snag, so pin the name before you register anything.

> **Recommendation.** Derive `HUB_HOST` from your namespace so it's unique and self-documenting — `<your-namespace>-jhub`, giving `https://<your-namespace>-jhub.nrp-nautilus.io`. Keep it short and stable: changing it later means re-issuing the CILogon callback and re-deploying. During NRP's migration from Ingress to the Gateway API, hosts may also be reachable on ports **50080/50443** (e.g. `https://<HUB_HOST>.nrp-nautilus.io:50443`).

### Rules the name must follow

`HUB_HOST` is a **DNS label**, so it is limited to lowercase letters, digits, and hyphens; it must
start and end with a letter or digit, and it can be at most 63 characters. Uppercase letters and
underscores are not legal. It also becomes the name of a Kubernetes TLS secret (`<HUB_HOST>-tls`),
which is a second reason to keep it short.

### Examples

Worked through with the namespace `caida-nids` — substitute your own:

| Candidate                   |                                                                                                           |
| --------------------------- | --------------------------------------------------------------------------------------------------------- |
| `caida-nids-jhub`           | ✅ the recommended shape — `<namespace>-jhub`                                                             |
| `caida-nids-jupyterhub`     | ⚠️ valid, just longer for nothing                                                                         |
| `jupyterhub`, `hub`, `nids` | ❌ generic: almost certainly claimed already, and claiming it takes the name from everyone else on NRP    |
| `CAIDA-NIDS`, `caida_nids`  | ❌ invalid — uppercase and underscores aren't legal in a DNS label                                        |
| `caida-nids-jhub-test2`     | ⚠️ fine for a throwaway hub, but renaming later means re-registering the CILogon callback and redeploying |

### Where the value ends up

Every one of these embeds the name you pick. With `HUB_HOST=caida-nids-jhub`:

| Setting                                                                           | Value                                                        |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| The URL you and your students visit                                               | `https://caida-nids-jhub.nrp-nautilus.io`                    |
| CILogon callback URL ([Step 5](#step-5-register-a-cilogon-oauth-application))     | `https://caida-nids-jhub.nrp-nautilus.io/hub/oauth_callback` |
| `ingress.hosts` and `ingress.tls[].hosts` ([values.yaml](../configs/values.yaml)) | `caida-nids-jhub.nrp-nautilus.io`                            |
| `ingress.tls[].secretName`                                                        | `caida-nids-jhub-tls`                                        |

### Is the name already taken?

You cannot tell from DNS. `*.nrp-nautilus.io` is a wildcard, so `dig` and `nslookup` return an
answer for _every_ candidate whether or not anything serves it. Ask over HTTP instead:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://caida-nids-jhub.nrp-nautilus.io
```

What you will typically see:

- **200 / 302 / 401** — an application is already answering on that host. Pick another name.
- **404**, or a TLS error because no certificate was ever issued for the host — nothing appears to
  have claimed it.

Treat that as a probe, not a guarantee: it reads whatever the ingress happens to return, and a name
can be claimed between your check and your deploy. The authoritative answer arrives at deploy time —
if the host is taken, your Ingress won't serve it and cert-manager won't issue its certificate.
Confirm with `kubectl get ingress -n <YOUR_NAMESPACE>` and `kubectl describe ingress -n <YOUR_NAMESPACE>`
after [deploying the hub](4_nrp_jupyterhub.md).

## Step 5: Register a CILogon OAuth Application

**Your own hub only.** Now that `HUB_HOST` is pinned, register the OAuth application the hub will
authenticate against — its callback URL embeds the hostname, which is why this comes before you
deploy anything.

Register at [https://cilogon.org/oauth2/register](https://cilogon.org/oauth2/register) with:

- **Callback URL** — `https://<HUB_HOST>.nrp-nautilus.io/hub/oauth_callback`
  (with the example above: `https://caida-nids-jhub.nrp-nautilus.io/hub/oauth_callback`)
- **Client Type** — Confidential
- **Scopes** — `org.cilogon.userinfo,openid,profile,email`
- **Refresh Tokens** — No

Save the issued **client ID** and **client secret**. They go into `hub.config.CILogonOAuthenticator`
when you deploy — see [JupyterHub](4_nrp_jupyterhub.md).

> **The callback URL must match exactly.** Registering against the wrong host is the most common
> setup failure, and it surfaces only at login time, after everything else looks healthy. If you
> change `HUB_HOST` later, come back and update this registration.

> **Never commit the client secret.** Keep it in an uncommitted Helm override or a Kubernetes
> secret — [JupyterHub](4_nrp_jupyterhub.md) covers the handling, and this repo's
> [.gitignore](../.gitignore) already excludes `secrets.values.yaml`.

## Next

**Community hub** — once your namespace is active you are done here. Log in at
[jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io), pick an instance sized
for your assignment, and confirm it works with [Verify](5_verify_hub.md).

**Your own hub** — continue to [Configure kubectl](3_kubectl_config.md) to point `kubectl` at NRP and your namespace — that guide also confirms your namespace access — then [JupyterHub](4_nrp_jupyterhub.md) to deploy your own JupyterHub into it. Carry three things forward: your namespace, your `HUB_HOST`, and the CILogon client ID and secret from Step 5.

## References

- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [NRP Documentation: Exposing HTTP (Ingress)](https://nrp.ai/documentation/userdocs/running/ingress/)
- [NRP Documentation: Gateway API](https://nrp.ai/documentation/userdocs/running/gateway/)
- [NRP Portal](https://portal.nrp-nautilus.io)
- [NRP Namespaces](https://nrp.ai/namespaces)
- [CILogon](https://www.cilogon.org/)

---

[Install kubectl](1_kubectl_install.md) | **NRP & Namespace** | [Configure kubectl](3_kubectl_config.md) | [JupyterHub](4_nrp_jupyterhub.md) | [Verify](5_verify_hub.md)
