# Combined container image for the NIDS JupyterHub (one image, three spawner profiles).
#
# Base image (RECOMMENDATION — confirm before production):
#   A Spark-capable Jupyter base so the JVM + Spark are preinstalled for the DNS
#   assignment (the only assignment that uses Spark). The BGP and telescope profiles are
#   pure Python and ignore the Spark bits. If you prefer a smaller footprint you
#   can split the DNS/Spark image off from a plain BGP+telescope image later.
#
# Confirm the base image ships a Python compatible with the pinned packages in
# requirements.txt before relying on it.
FROM quay.io/jupyter/all-spark-notebook:latest

# --- Python dependencies (union of the three assignment notebooks) ---
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

# Build & push to the NRP GitLab registry, e.g.:
#   docker build -t gitlab-registry.nrp-nautilus.io/<group>/<project>/nids-hub:latest image/
#   docker push  gitlab-registry.nrp-nautilus.io/<group>/<project>/nids-hub:latest
# (ideally automated via NRP GitLab CI/CD).
