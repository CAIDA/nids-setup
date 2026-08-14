# UCSD-NT FlowTuple v4 (Avro, SDSC Expanse)

The UCSD Network Telescope's aggregated FlowTuple v4 archive, in Avro, read with Spark on SDSC
Expanse. The full-scale counterpart to the two anonymized PCAP samples.

- **Used by:** UCSDNT
- **Produced by:** CAIDA — UCSD Network Telescope
- **Served from:** **Not NRP.** SDSC Expanse via Slurm/Singularity, against
  `https://hermes.caida.org`
- **Public version usable:** **No** — credentialed bucket, and an Expanse allocation is required
- **Setup:** ✅ documented below, with the credential-issuance step a gap
- **Credentials:** `UCSD_NT_S3_ACCESS_KEY`, `UCSD_NT_S3_SECRET_KEY`; plus `ETP26_ACCOUNT` for the
  Lustre output path
- **Time-sensitive:** Yes — `year=`/`month=`/`day=` partitions, and the bucket name carries a year
- **Licence / governance:** AUA/DUA-governed; raw telescope data stays on Expanse

> **This assignment does not run on the NRP hub.** Everything else in this directory is about a
> JupyterHub on NRP; this one is HPC. It is documented here so the inventory is complete, not because
> the hub needs it. It is also the one assignment with **no `00-environment-check.ipynb`**, because
> the environment it targets is Slurm, not JupyterHub.

## Access

S3-compatible object store, addressed two ways: `boto3` for listing, Spark/S3A for reading.

```python
S3_ENDPOINT_URL = 'https://hermes.caida.org'
S3_BUCKET       = 'telescope-ucsdnt-avro-flowtuple-v4-2026'
prefix = f'datasource=ucsd-nt/year={day.year:04d}/month={day.month:02d}/day={day.day:02d}/'
```

**boto3** — note the signature version and path addressing; neither is default:

```python
from botocore.config import Config
config = Config(signature_version='s3v4', s3={'addressing_style': 'path'})
```

**Spark/S3A** — the settings that differ from the OpenINTEL configuration are the interesting ones:

```python
'spark.hadoop.fs.s3a.aws.credentials.provider':
    'org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider'   # NOT Anonymous
'spark.hadoop.fs.s3a.path.style.access':  'true'
'spark.hadoop.fs.s3a.endpoint.region':    'us-east-1'
'spark.hadoop.fs.s3a.analytics.accelerator.enabled': 'false'
'spark.sql.execution.arrow.pyspark.enabled':         'false'
'spark.jars.packages':
    'org.apache.spark:spark-avro_2.13:4.2.0,org.apache.hadoop:hadoop-aws:3.5.0'
```

- **`SimpleAWSCredentialsProvider`, not `AnonymousAWSCredentialsProvider`.** This is the opposite of
  [openintel-fdns](../openintel-fdns/), and the two configurations are otherwise similar enough to
  copy the wrong one.
- `endpoint.region=us-east-1` is required even though the store is not AWS.
- The Spark JARs are a **different set** from the DNS assignment's — `spark-avro` plus
  `hadoop-aws:3.5.0`, versus `hadoop-aws:3.4.0` + the AWS SDK bundle. The `nids-hub` image pre-stages
  the DNS pair, not these.
- Object keys end `.<epoch>.flowtuple-v4.avro`, matched with `\.(\d+)\.flowtuple-v4\.avro$` to
  recover the timestamp. Roughly 288 files per day (one per five-minute bin).
- `local[$SLURM_CPUS_PER_TASK]` with `spark.driver.memory` matched to the Slurm/`galyleo` allocation —
  in local mode the driver hosts all executors, so this is the setting that governs whether a day's
  read fits in memory.

## Concrete values in use today

| item | value | source |
|---|---|---|
| endpoint | `https://hermes.caida.org` | `nids-ucsdnt-expanse-key/ir_traffic_prototype.ipynb:109` |
| bucket | `telescope-ucsdnt-avro-flowtuple-v4-2026` | `:110` |
| prefix | `datasource=ucsd-nt/year=<Y>/month=<M>/day=<D>/` | `:235` |
| test dates | `2026-02-14`, `2026-02-15` | `ir_traffic_prototype.ipynb` |
| full range | `2026-02-10` … `2026-03-05` | same |
| geo filter | `netacq_country` = `IR` | same |
| output | `/expanse/lustre/projects/<ETP26_ACCOUNT>/<USER>/output/prototype` | same |

The bucket name embeds `2026`. A different year of telescope data is a **different bucket**, not a
different prefix.

## Validate

`boto3` HEAD/listing against the bucket prefix, runnable only when both credentials are set. Skipped
with a clear note otherwise — a missing credential is not a failure, it means this dataset is out of
scope for whoever is running the check.

Not covered by [notebooks/check-datasets.ipynb](../../notebooks/check-datasets.ipynb): the hub is the
wrong environment for it.

## Setup

### 1. Obtain credentials — **gap**

`UCSD_NT_S3_ACCESS_KEY` and `UCSD_NT_S3_SECRET_KEY` are real AWS-style keys for
`hermes.caida.org`. **Who issues them, under what agreement, and how they are delivered is not
recorded anywhere.** Since the underlying data is AUA/DUA-governed, this step almost certainly
involves a data-use agreement — recover the process before promising a class access.

### 2. Obtain an Expanse allocation

`ETP26_ACCOUNT` names the SDSC project used for both the Slurm allocation and the Lustre output path
`/expanse/lustre/projects/<ETP26_ACCOUNT>/<USER>/output/`. **[unverified]** how the account is
requested.

### 3. Place the credentials file

Keys live in a git-ignored `.ucsdnts3.env`, loaded two ways depending on how the code runs:

- **Interactively** — via `%dotenv` / `%env` in the notebook.
- **Batch** — `singularity exec --env-file .ucsdnts3.env …` in the Slurm script.

Follow the module convention: commit a `.ucsdnts3.env.example` with empty values and keep the real
file ignored. This repo's `.gitignore` covers `*.env`.

### 4. Launch

`galyleo launch` with a memory allocation matched to `spark.driver.memory` (the recorded
configuration pairs a 24 g driver with a 32 GB allocation), or submit the Slurm array job, one task
per date.

### Refreshing to a newer period

Within the same year, change the date range and the partition prefix follows automatically. Crossing
a year boundary means a **new bucket name** — update `S3_BUCKET` as well, and expect the credentials
to need re-checking against it.

## See also

- `nids-ucsdnt-expanse/Datasets.md`, `nids-ucsdnt-expanse/PySpark-Parquet.md`
- [ucsd-nt-pcap-samples](../ucsd-nt-pcap-samples/) — the anonymized, open, NRP-hosted telescope data
- [openintel-fdns](../openintel-fdns/) — the other S3A configuration, deliberately different
