# ITDK router-level topology (Postgres)

CAIDA's Internet Topology Data Kit, loaded from release bz2 files into a Postgres database deployed
in the class namespace. Students query it with SQL rather than parsing the raw files.

- **Used by:** ITDK
- **Produced by:** CAIDA
- **Served from:** An in-namespace Postgres deployment (not Ceph, not external)
- **Public version usable:** **No** — the ITDK release files are public, but the assignment reads a
  built database that does not exist until someone builds it
- **Setup:** ✅ required, and documented below
- **Credentials:** `ITDK_READ_DSN` (read-only), from a `db_credentials.env` beside the notebook.
  `ITDK_CREDS_FILE` overrides the path; the builder uses `ITDK_BUILD_DSN`.
- **Time-sensitive:** Yes — the loader targets a dated release (`ITDK-2026-03`)
- **Licence / governance:** open

> **No Postgres instance exists in this repo.** `configs/` carries no manifest and no profile
> provisions one. An ITDK profile without a database spawns a notebook that cannot connect — the same
> shape of gap as [iyp-neo4j](../iyp-neo4j/). **This dataset is not part of release 1**; the
> assignment is out of scope until an instance exists.

## Access

```python
from sqlalchemy import create_engine
engine = create_engine(READ_DSN)          # from ITDK_READ_DSN
```

Schema `caida_itdk`, four tables:

| table | contents |
|---|---|
| `itdk_node_as` | `node_id`, `asn`, `method` — AS assignment per router node |
| `itdk_node_geolocation` | per-node location |
| `itdk_link_endpoints` | router-level links |
| `itdk_router_hostnames` | hostnames per router |

Every node-keyed table is restricted to nodes appearing in CAIDA's authoritative "most likely
routers" set, so the database describes known routers only rather than all observed nodes.

Host depends on where the notebook runs: the in-cluster Service name when the hub shares the
namespace, or `127.0.0.1` through a `kubectl port-forward` tunnel otherwise.

## Concrete values in use today

| item | value | source |
|---|---|---|
| release | `ITDK-2026-03`, IPv4 `midar-iff-snmp` topology | `nids-itdk-key/nids-itdk-build-db.ipynb:88-94` |
| source files | `midar-iff-snmp.nodes.as.bz2`, `.nodes.geo.bz2`, `.links.bz2`, `.routers.bz2` | same |
| schema | `caida_itdk` | same |
| read credential | `ITDK_READ_DSN` in `db_credentials.env` | `nids-itdk-key/00-environment-check.ipynb` |

The loader defines **four** source files. `nids-itdk-key/README-ready-to-go.md:16` and the build
notebook's own header both say "five source files" — that count is stale, not a missing file.

## Validate

Three steps, all credential-gated:

1. Connect and `SELECT 1`.
2. Confirm the four tables exist in `information_schema.tables` under `table_schema='caida_itdk'`.
3. Read one row from `caida_itdk.itdk_node_as`.

The DSN is never printed — only `user@host:port/db`, rendered through SQLAlchemy's `make_url`.

## Setup

A complete pipeline exists. The steps below are reconstructed from
`nids-itdk-key/Setup.md`, `nids-itdk-key/postgres.yaml`, and
`nids-itdk-key/nids-itdk-build-db.ipynb` — all of which live in a **private** answer-key repo, which
is why they are written out here rather than linked.

### 1. Deploy Postgres into the namespace

NRP does not allow exposing TCP services like 5432 to the public internet, so the deployment is a
PVC + Deployment + **ClusterIP** Service — reachable in-cluster, tunnelled for anything else.

Sizing that matters: the four retained tables total roughly 97 GB with indexes, so the PVC is
provisioned at **150Gi** to leave headroom for WAL and `CREATE INDEX` temporary space during the
build. The stock example in `Setup.md` asks for 10Gi and will not survive a full load.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 150Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-deployment
spec:
  replicas: 1
  selector:
    matchLabels: {app: postgres}
  template:
    metadata:
      labels: {app: postgres}
    spec:
      containers:
        - name: postgres
          image: postgres:15
          resources:
            limits: {memory: 2Gi, cpu: 1}
            requests: {memory: 1Gi, cpu: 500m}
          env:
            - {name: POSTGRES_USER, value: "nrp_user"}
            - {name: POSTGRES_PASSWORD, value: "CHANGE_ME"}
            - {name: POSTGRES_DB, value: "nrp_db"}
          ports: [{containerPort: 5432}]
          volumeMounts:
            - {mountPath: /var/lib/postgresql/data, name: pgdata}
      volumes:
        - name: pgdata
          persistentVolumeClaim: {claimName: postgres-pvc}
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
spec:
  type: ClusterIP
  ports: [{port: 5432, targetPort: 5432}]
  selector: {app: postgres}
```

Set a real password before applying, keep the filled-in file out of git (this repo's `.gitignore`
covers `*.secret.yaml` and `*.env`), then:

```bash
kubectl apply -f postgres.secret.yaml -n <YOUR_NAMESPACE>
kubectl get pods -n <YOUR_NAMESPACE>
```

### 2. Stage the ITDK release files

The loader reads four bz2 files from `ITDK_DATA_DIR`. It accepts either a directory already holding
them, or a release archive root — in which case it auto-selects the most recent `ITDK-YYYY-MM/`
subdirectory that contains all of them (`ITDK-YYYY-MM` sorts correctly as a plain string).

CAIDA's shared archive path `/data/topology/ITDK` is the default source. **[unverified]** whether
that path is reachable from the machine running the build, or how to obtain the release otherwise.

The build verifies the geolocation file's md5 before touching any table, so a truncated download
fails fast rather than half-loading.

### 3. Load the database

From a machine with the files staged, tunnel to the pod and run the loader:

```bash
kubectl port-forward svc/postgres-service 5432:5432 -n <YOUR_NAMESPACE>
```

Then run `nids-itdk-build-db.ipynb` with `ITDK_BUILD_DSN` pointed at `127.0.0.1:5432`. Its SETUP cell
runs once per session; each table then has one standalone, idempotent cell doing
`DROP … CASCADE → CREATE → COPY-load → index → ANALYZE`, so a failure only requires re-running that
one cell.

### 4. Issue the read-only credential

Create a read-only Postgres role and distribute its DSN as `ITDK_READ_DSN` in a `db_credentials.env`
placed beside the student notebook. Postgres has real role-based access control, so unlike
[iyp-neo4j](../iyp-neo4j/) this credential is genuinely read-only and the restriction is enforced by
the database rather than by convention. **[unverified]** — the exact `GRANT` statements are not
recorded in any repo and should be written down when next run.

### Refreshing to a newer release

Change the `ITDK-YYYY-MM` release staged into `ITDK_DATA_DIR` and re-run the load cells; the loader
picks the most recent release automatically and each cell drops and rebuilds its own table. Update
the expected geolocation md5 to match the new release, and the release name in this file's values
table.

## See also

- `nids-itdk/Datasets.md`, `nids-itdk/SQL.md`
- [iyp-neo4j](../iyp-neo4j/) — the other database-backed assignment, same shape of gap
