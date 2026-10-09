# ITDK router-level topology (Postgres)

CAIDA's Internet Topology Data Kit, loaded from release bz2 files into a Postgres database deployed
in the class namespace. Students query it with SQL rather than parsing the raw files.

- **Used by:** ITDK
- **Produced by:** CAIDA
- **Served from:** An in-namespace Postgres deployment (not Ceph, not external)
- **Public version usable:** **No** — the assignment reads a built database that does not exist
  until an instructor builds it, and the pinned release is not yet public
- **Setup:** ✅ required, by the instructor — see below
- **Credentials:** `ITDK_READ_DSN` (read-only), from a `db_credentials.env` beside the notebook.
  `ITDK_CREDS_FILE` overrides the path; the builder uses `ITDK_BUILD_DSN`.
- **Time-sensitive:** Yes — the loader targets a dated release (`ITDK-2026-03`)
- **Licence / governance:** open

> **Each class needs its own database.** The instructor deploys Postgres into their NRP namespace
> and builds it from the ITDK release; nothing here provisions one. The steps, and the manifest,
> are in the answer-key repo's README (`nids-itdk-key`). **The release the key pins,
> `ITDK-2026-03`, is not in the public ITDK archive** (latest public: `2025-08`, checked
> 2026-10-09), so an outside instructor cannot yet build the pinned database.

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
| read credential | `ITDK_READ_DSN` in `db_credentials.env` | `nids-itdk-key/README.md` §4 |

The loader defines **four** source files. The build notebook's own comments say "five" — that count
is stale, not a missing file.

## Validate

Three steps, all credential-gated:

1. Connect and `SELECT 1`.
2. Confirm the four tables exist in `information_schema.tables` under `table_schema='caida_itdk'`.
3. Read one row from `caida_itdk.itdk_node_as`.

The DSN is never printed — only `user@host:port/db`, rendered through SQLAlchemy's `make_url`.

## Setup

Follow `nids-itdk-key/README.md`: deploy `postgres.yaml` (150Gi volume, ClusterIP Service, password
in a Kubernetes secret), build with `nids-itdk-build-db.ipynb`, create the read-only `nidsitdk`
role, and hand students `ITDK_READ_DSN`. From any JupyterHub inside NRP, the host is
`postgres-service.<YOUR_NAMESPACE>.svc.cluster.local:5432`; this works across namespaces.
NRP deletes Deployments after two weeks unless the namespace has an exception, but the data
survives on the volume and `kubectl apply` brings the database back.

### Refreshing to a newer release

Change the `ITDK-YYYY-MM` release staged into `ITDK_DATA_DIR` and re-run the load cells; the loader
picks the most recent release automatically and each cell drops and rebuilds its own table. Update
the expected geolocation md5 to match the new release, and the release name in this file's values
table.

## See also

- `nids-itdk/Datasets.md`, `nids-itdk/SQL.md`
- [iyp-neo4j](../iyp-neo4j/) — the other database-backed assignment, same shape of gap
