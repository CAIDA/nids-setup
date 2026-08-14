# OpenINTEL forward-DNS zonefile Parquet

Daily active-DNS measurements of entire TLD zones, published by OpenINTEL as partitioned Parquet in a
public S3-compatible object store. Read with Spark over S3A.

- **Used by:** DNS
- **Produced by:** External — OpenINTEL
- **Served from:** Both — external egress to `object.openintel.nl`
- **Public version usable:** Yes — anonymous, open access, no registration
- **Setup:** none needed
- **Credentials:** none (`AnonymousAWSCredentialsProvider`)
- **Time-sensitive:** Yes — `year=`/`month=`/`day=` partitions
- **Licence / governance:** open

## Access

PySpark in local mode against S3A. The configuration below is the one the assignment itself uses;
every S3A setting in it is load-bearing.

```python
OI_ENDPOINT  = "https://object.openintel.nl"
OI_BUCKET    = "openintel-public"
OI_FDNS_BASE = "fdns/basis=zonefile"

conf = SparkConf()
conf.setMaster("local[*]")
conf.set("spark.executor.memory", "8G")
conf.set("spark.driver.memory", "8G")
conf.set("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
conf.set("fs.s3a.aws.credentials.provider",
         "org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider")
conf.set("fs.s3a.endpoint", OI_ENDPOINT)
conf.set("fs.s3a.connection.ssl.enabled", "true")
conf.set("fs.s3a.path.style.access", "true")
conf.set("fs.s3a.block.size", "64M")
conf.set("fs.s3a.readahead.range", "4M")
conf.set("fs.s3a.vectored.io.enabled", "false")
conf.set("parquet.hadoop.vectored.io.enabled", "false")
conf.set("spark.sql.parquet.mergeSchema", "false")
conf.set("spark.sql.parquet.filterPushdown", "true")
conf.set("spark.jars.packages",
         "org.apache.hadoop:hadoop-aws:3.4.0,software.amazon.awssdk:bundle:2.24.6")
```

Partition path, then a partition-aware read:

```python
base = f"s3a://{OI_BUCKET}/{OI_FDNS_BASE}"
path = f"{base}/source={source}/year={year}/month={month:02d}/day={day:02d}"
df = spark.read.option("basePath", base + "/").parquet(path)
```

- **`fs.s3a.vectored.io.enabled` and `parquet.hadoop.vectored.io.enabled` must both stay `false`.**
  Enabling either breaks reads against this store. Do not "optimize" them.
- `month` and `day` are zero-padded. `month=1` will not match a partition.
- `basePath` is what lets Spark infer the partition columns; without it the `source`/`year`/`month`/
  `day` fields are lost.
- **First run is slow.** `spark.jars.packages` resolves through Ivy from Maven Central and can take
  minutes in a fresh home directory. The `nids-hub` image pre-stages both JARs into
  `$SPARK_HOME/jars`; on the hosted NRP hub they are fetched over the network instead.

### Available sources

Open access, no registration. Sizes are approximate daily domain counts.

| `source=` | available from | size |
|---|---|---|
| `gov` | 2017-05-01 | smallest — good for a probe |
| `se` | 2016-06-07 | ~1 M — **the graded source** |
| `nu` | 2016-06-07 | |
| `ee` | 2019-07-29 | |
| `ch` | 2020-05-19 | |
| `li` | 2020-05-19 | ~85 k |
| `sk` | 2022-05-11 | |
| `fr` | 2022-08-10 | ~4 M |

`.com` and `.nl` exist upstream but are not in the open-access set.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| DNS (graded) | `source=se/year=2024/month=01/day=15` | `nids-dns-ecosystem-key/nids-dns-ecosystem-key.ipynb:276,153-162` |
| DNS (longitudinal) | `source=se`, `year` in 2019–2024, same `month=01/day=15` | `nids-dns-ecosystem-key/nids-dns-ecosystem-key.ipynb:573` |
| DNS (reachability probe) | `source=gov/year=2024/month=01/day=15` | `nids-dns-ecosystem-key/00-environment-check.ipynb:214` |

The environment check deliberately probes `gov` — the smallest source — and sets driver/executor
memory to `4G` rather than the `8G` above. Every S3A setting is identical between the two; only the
memory and the Spark `appName` differ.

## Validate

Read one partition's Parquet **schema**, not its rows. That exercises the endpoint, the anonymous
credential provider, path-style addressing, and the JAR set, without pulling data.

Expect the first run to be slow if the JARs are not pre-staged. This is the slowest check in the
suite.

## See also

- `nids-dns-ecosystem/Datasets.md`, `nids-dns-ecosystem/Spark.md`
- `nids-dns-ecosystem-key/openintel_csv/openintel_data_dictionary.md` — column-level schema
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the
  `object.openintel.nl` and Maven Central egress rows
