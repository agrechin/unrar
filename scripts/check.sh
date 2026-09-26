#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
image=unrar-checks:local
docker build --tag "$image" --file "$root/docker/Dockerfile" "$root"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$root,target=/src,readonly" \
  "$image" bash /src/scripts/check-container.sh
