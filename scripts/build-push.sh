#!/usr/bin/env bash
# Build the combined NIDS JupyterHub image and push it to a container registry.
# Full walkthrough: docs/0_build_images.md
#
# Usage:
#   IMAGE=caida/nids-hub scripts/build-push.sh
#   IMAGE=ghcr.io/caida/nids-hub scripts/build-push.sh --no-cache
#
# Environment:
#   IMAGE     required. Registry path WITHOUT a tag, e.g. caida/nids-hub
#   PLATFORM  target architecture. Default linux/amd64 -- do not change without
#             reading the architecture note in docs/0_build_images.md.
#   TAG       immutable tag to publish alongside :latest. Default: git short SHA.
#
# Any extra arguments are passed through to `docker buildx build`.

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE to the registry path without a tag, e.g. IMAGE=caida/nids-hub}"
PLATFORM="${PLATFORM:-linux/amd64}"

# CDPATH must be cleared and cd's stdout discarded: with CDPATH set, cd echoes the
# directory it resolved, which would end up inside REPO_ROOT.
CDPATH=''
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." > /dev/null && pwd)"
TAG="${TAG:-$(git -C "$REPO_ROOT" rev-parse --short HEAD)}"

# The SHA tag is only meaningful if it describes what was actually built.
if [ -n "$(git -C "$REPO_ROOT" status --porcelain -- image/)" ]; then
  echo "WARNING: image/ has uncommitted changes, so :$TAG will not describe this build." >&2
  echo "         Commit first, or pass an explicit TAG=..." >&2
fi

echo "Building $IMAGE for $PLATFORM"
echo "  tags: $TAG, latest"
echo "  context: $REPO_ROOT/image"

# --provenance=false keeps the push a plain single-arch manifest rather than an
# attestation index. --platform is mandatory: NRP's nodes are predominantly x86 and
# an arm64 image fails at pod start with "exec format error".
docker buildx build \
  --platform "$PLATFORM" \
  --provenance=false \
  -t "$IMAGE:$TAG" \
  -t "$IMAGE:latest" \
  --push \
  "$@" \
  "$REPO_ROOT/image"

echo
echo "Published:"
echo "  $IMAGE:$TAG"
echo "  $IMAGE:latest"
echo
echo "To pin the hub to this exact build, set in configs/values.yaml:"
echo "  singleuser.image.name: $IMAGE"
echo "  singleuser.image.tag:  $TAG"
