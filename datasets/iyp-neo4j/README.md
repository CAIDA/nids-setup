# IYP (Internet Yellow Pages) Neo4j graph

The Internet Yellow Pages: a labelled property graph joining AS, prefix, IXP, country and ranking data
from many sources, queried with Cypher over the Bolt protocol.

- **Used by:** IYP
- **Produced by:** External — IIJ Lab; public instance operated by IHR
- **Served from:** Both — the public instance is external; a self-hosted instance would be in-cluster
- **Public version usable:** **Yes** for students — the public IHR instance needs no credentials. The
  self-hosted instructor instance is a separate thing and does not exist yet.
- **Setup:** ✅ documented below for the self-hosted path; none needed for the student path
- **Credentials:** none for the public instance. `IYP_READ_URI`, `IYP_READ_USER`,
  `IYP_READ_PASSWORD` from a `neo4j_credentials.env` for the self-hosted one.
- **Time-sensitive:** Live — the public instance is continuously updated, with no pinned snapshot
- **Licence / governance:** open

## Access

### Student path — public IHR instance

```python
from neo4j import GraphDatabase

IYP_URI = "neo4j://iyp-bolt.ihr.live:7687"
db = GraphDatabase.driver(IYP_URI, auth=None)
db.verify_connectivity()
```

`auth=None` is correct — the instance is genuinely open, not an omission.

Because the graph is live and unpinned, a query run today can return different numbers tomorrow. The
key notebook prints its run date so results can be reported alongside it; do the same for anything
derived from this dataset.

### Instructor path — self-hosted instance

Not deployed. Credentials read from a `neo4j_credentials.env` beside the notebook:

```
IYP_READ_URI=bolt://localhost:7687      # via kubectl port-forward
IYP_READ_USER=neo4j
IYP_READ_PASSWORD=...
```

Two addressing modes: the in-cluster Service address when the hub shares the instance's namespace, or
a `kubectl port-forward` tunnel to `bolt://localhost:7687` otherwise.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| IYP | `neo4j://iyp-bolt.ihr.live:7687`, `auth=None` | `nids-iyp-key/nids-iyp-key.ipynb:85-87`, `nids-iyp/Datasets.md:76-80` |

`nids-iyp` has **no `00-environment-check.ipynb`** — unlike the six assignments that do. Until it
gets one, [notebooks/check-datasets.ipynb](../../notebooks/check-datasets.ipynb) is the only automated
check that the IYP endpoint is reachable from the hub.

## Validate

`GraphDatabase.driver(uri, auth=None)` followed by `db.verify_connectivity()`. This is a Bolt
handshake, not an HTTP request — it exercises a protocol and a port nothing else in the suite uses.

## Setup

Only for the self-hosted instructor instance. **This instance does not exist**, and neither does the
`docs/1_deploy_iyp_neo4j.md` that `neo4j_credentials.env` and the pod manifest both reference — that
file is absent from every NIDS repository. What follows is reconstructed from
`nids-iyp/temp/configs/iyp-neo4j-pod.secret.yaml`, which is intact and heavily commented; the gaps
are called out explicitly rather than guessed.

> ⚠️ **Neo4j Community Edition has no role-based access control.** There is no database-enforced way
> to issue a read-only credential — the notebook's keyword filter is a courtesy check, not a security
> boundary. A hosted hub hands the same shared-trust credential to every student, any one of whom
> could delete the graph. Weigh restore-from-pinned-dump on a schedule, a read-only replica, or a
> Bolt-level proxy before going live. **No instance exists yet**, so the instructor path for this
> module is unbuilt; the student path against the public instance is unaffected.

### 1. Obtain the IYP dump — **gap**

The pod loads a Neo4j dump from `/data/dumps` on first start. **Which dump, from where, and how it
reaches that path is not recorded anywhere.** IYP publishes periodic dumps; which release was pinned,
and whether it was copied into the PVC by hand or by a job, must be recovered before this procedure
is runnable.

### 2. Provision storage — **gap**

The pod mounts a PVC named `iyp-storage`. **No manifest defining that PVC exists** in any repo — only
the reference to it. Its size must accommodate the dump plus the loaded store.

### 3. Deploy the pod

The manifest is a single Pod: an init container that loads the dump once, then Neo4j serving HTTP
(7474) and Bolt (7687) off the loaded database. Copy it to a git-ignored
`configs/iyp-neo4j.secret.yaml`, replace the password, and apply that copy.

Load-bearing details, each of which the manifest's own comments flag:

- **The two images must stay on matching versions** — `neo4j/neo4j-admin:2025-community-debian` and
  `neo4j:2025-community`. `neo4j-admin` writes a store format only its own generation of Neo4j opens.
- **`NEO4J_AUTH` is read only on the first init of an empty data directory.** Whatever is set on the
  first successful start is the password for the life of the PVC; editing and re-applying later does
  nothing.
- The init container is the **memory high-water mark of the whole deployment** — 8Gi requested, 16Gi
  limit — and will OOM below it. It runs only once.
- `NEO4J_server_directories_data=/data`; Neo4j appends `databases/` and `transactions/` itself, which
  is where the init container puts them.
- `NEO4J_db_recovery_fail__on__missing__files=false` — a dump carries no transaction logs, and
  recovery otherwise refuses to start on a freshly loaded database.
- `NEO4J_dbms_connector_bolt_tls__level=DISABLED` — clients connect over plain `bolt://` through a
  port-forward or the in-cluster Service; there is no certificate on 7687.
- `NEO4J_dbms_security_procedures_unrestricted=gds.*,apoc.*`.
- The init container is idempotent: it skips the load if `/data/databases/neo4j` already exists.

### 4. Expose it and distribute credentials — **partial gap**

The manifest defines a Pod but **no Service**, so in-cluster access by name needs one adding; the
recorded working configuration uses a port-forward instead:

```bash
kubectl port-forward pod/iyp-neo4j 7474:7474 7687:7687 -n <YOUR_NAMESPACE>
```

Distribute `IYP_READ_URI` / `IYP_READ_USER` / `IYP_READ_PASSWORD` as a `neo4j_credentials.env` beside
the notebook, git-ignored, with a committed `.env.example` alongside it. Given the RBAC gap above,
decide the credential-distribution model before handing this to a class.

### Refreshing to a newer dump

`NEO4J_AUTH` and the loaded store are both tied to the PVC's lifetime, and the init container skips
the load whenever a database is already present. Refreshing therefore means replacing the dump **and**
clearing `/data/databases`, or provisioning a fresh PVC — not simply re-applying the pod.

## See also

- `nids-iyp/Datasets.md`, `nids-iyp/Cypher.md`
- `nids-iyp/checkpoint.md` — the module's own status/handoff record
- [itdk-postgres](../itdk-postgres/) — the other database-backed assignment
