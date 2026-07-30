# Combined container image for the NIDS JupyterHub (one image, one profile per assignment).
#
# Base image (RECOMMENDATION — confirm before production):
#   A Spark-capable Jupyter base so the JVM + Spark are preinstalled for the DNS
#   assignment (the only assignment that uses Spark). The BGP and telescope profiles are
#   pure Python and ignore the Spark bits. If you prefer a smaller footprint you
#   can split the DNS/Spark image off from a plain BGP+telescope image later.
#
# Pinned by digest, not by :latest. The tag is mutable, and every time it moves the
# CI build's layer cache is fully invalidated — turning a one-line change back into a
# cold multi-GB rebuild. This is the OCI *image index* digest, so it still resolves
# per-architecture; do NOT replace it with a platform-specific manifest digest or the
# build will fail on a runner of the other architecture.
#
# Resolved 2026-07-29 (index: linux/amd64 + linux/arm64). To bump deliberately:
#   curl -sI -H "Accept: application/vnd.oci.image.index.v1+json" \
#     https://quay.io/v2/jupyter/all-spark-notebook/manifests/latest \
#     | grep -i docker-content-digest
# Confirm the new base still ships a Python compatible with requirements.txt.
FROM quay.io/jupyter/all-spark-notebook@sha256:34354ca8fa27633019ad0913a6b9e6e168cff33b1c71019cc87881047ded88df

# --- Python dependencies (union of the assignment notebooks) ---
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# --- Pre-stage the DNS assignment's Spark S3A JARs -------------------------------
# The DNS notebook otherwise pulls these via `spark.jars.packages` from Maven
# Central at SparkSession start. Baking them into $SPARK_HOME/jars removes that
# runtime egress dependency. Versions come from nids-dns-ecosystem-key.ipynb:
#   org.apache.hadoop:hadoop-aws:3.4.0
#   software.amazon.awssdk:bundle:2.24.6
USER root
ARG HADOOP_AWS_VERSION=3.4.0
ARG AWS_SDK_BUNDLE_VERSION=2.24.6
ARG MAVEN=https://repo1.maven.org/maven2
RUN set -eux; \
    curl -fSL -o "${SPARK_HOME}/jars/hadoop-aws-${HADOOP_AWS_VERSION}.jar" \
      "${MAVEN}/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar"; \
    curl -fSL -o "${SPARK_HOME}/jars/bundle-${AWS_SDK_BUNDLE_VERSION}.jar" \
      "${MAVEN}/software/amazon/awssdk/bundle/${AWS_SDK_BUNDLE_VERSION}/bundle-${AWS_SDK_BUNDLE_VERSION}.jar"
USER ${NB_UID}

# Built and pushed by ../.gitlab-ci.yml on NRP GitLab CI/CD — see docs/4_nrp_gitlab.md.
# The pipeline builds with Kaniko using build context image/, and publishes both
#   gitlab-registry.nrp-nautilus.io/<group>/<project>/nids-hub:latest
#   gitlab-registry.nrp-nautilus.io/<group>/<project>/nids-hub:<short-sha>
#
# Fallback only, if CI is unavailable (see "Building locally instead" in doc 4).
# --platform linux/amd64 is NOT optional on Apple Silicon or any ARM machine: NRP's
# nodes are predominantly x86, and an arm64 image fails at pod start with
# "exec format error".
#   docker build --platform linux/amd64 \
#     -t gitlab-registry.nrp-nautilus.io/<group>/<project>/nids-hub:latest image/
#   docker push gitlab-registry.nrp-nautilus.io/<group>/<project>/nids-hub:latest
