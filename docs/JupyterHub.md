# Running Your Own JupyterHub in Your NRP Namespace

This guide walks through deploying a private JupyterHub into your own NRP Nautilus namespace via Helm, instead of using the public shared hub.

## Prerequisites

- Completed [Namespace.md](Namespace.md) — you need an active namespace and `kubectl` pointed at it.
- [Helm](https://helm.sh/docs/intro/install/) installed locally.

## Step 1: Register a CILogon OAuth Client

Your hub needs its own OAuth client so users can log in via CILogon:

1. Go to the [CILogon OAuth registration page](https://cilogon.org/oauth2/register) (linked from the [NRP JupyterHub deploy guide](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub/)).
2. Register a new client, providing:
   - A callback URL matching your future hub hostname, e.g. `https://<your-hub-hostname>/hub/oauth_callback`.
3. Save the issued **client ID** and **client secret** — you'll need them in `values.yaml` below.

## Step 2: Add the JupyterHub Helm Repo

```bash
helm repo add jupyterhub https://hub.jupyter.org/helm-chart/
helm repo update
```

## Step 3: Write `values.yaml`

Create a `values.yaml` for your deployment covering authentication, ingress, and storage. Key sections (see the [NRP JupyterHub deploy guide](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub/) for the full example):

- **hub.config** — configure the CILogon authenticator with your client ID/secret from Step 1.
- **proxy / ingress** — hostname and TLS, using NRP's `ingress-nginx` and `cert-manager`.
- **singleuser** — image, resource requests/limits, and storage class (`rook-ceph-block` for per-user `ReadWriteOnce` volumes).

## Step 4: Deploy

```bash
helm upgrade --install jhub jupyterhub/jupyterhub \
  --namespace <YOUR_NAMESPACE> \
  -f values.yaml
```

## Step 5: Verify

```bash
kubectl get pods -n <YOUR_NAMESPACE>
```

Once the hub pod is running, visit your hub's hostname, log in via CILogon, and spawn a server to confirm everything works end to end.

## Optional: Shared Storage Across User Servers

By default each user gets an isolated `ReadWriteOnce` (RWO) volume. To share a directory (e.g. a common dataset) across multiple user servers concurrently, use a `ReadWriteMany` (RWX) `rook-cephfs` volume instead of `rook-ceph-block`.

Add it under the `singleuser.storage` block via `extraVolumes` / `extraVolumeMounts` in the `kubespawner_override`, mounting it at a shared path, e.g. `/home/shared`:

```yaml
singleuser:
  storage:
    extraVolumes:
      - name: shared-data
        persistentVolumeClaim:
          claimName: <your-shared-rwx-pvc>
    extraVolumeMounts:
      - name: shared-data
        mountPath: /home/shared
```

See the storage configuration section of the [NRP JupyterHub deploy guide](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub/) for the full snippet and details on `rook-ceph-block` vs `rook-cephfs`.

## Optional: Real-Time Collaboration (Shared Server Access)

If you want multiple users to log into the *same running server* simultaneously, enable the `shares` scope via JupyterHub's RBAC configuration. See [JupyterHub: Sharing access to user servers](https://jupyterhub.readthedocs.io/en/stable/reference/sharing.html).

## Troubleshooting

- **Pod stuck in `Pending`** — check `kubectl describe pod <pod> -n <YOUR_NAMESPACE>` for resource quota or scheduling issues.
- **OAuth callback mismatch** — ensure the callback URL registered with CILogon in Step 1 exactly matches your hub's hostname and path.

## References

- [NRP Documentation: Deploy JupyterHub](https://nrp.ai/documentation/userdocs/jupyter/jupyterhub/)
- [NRP Documentation: Getting Started](https://nrp.ai/documentation/userdocs/start/getting-started/)
- [JupyterHub Core Reference: Configuring User Environments](https://jupyterhub.readthedocs.io/en/stable/reference/config-user-env.html)
- [JupyterHub Core Reference: Sharing Access to User Servers](https://jupyterhub.readthedocs.io/en/stable/reference/sharing.html)
