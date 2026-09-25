#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
bash "$root/scripts/build.sh" --tools-only
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$root,target=/src,readonly" \
  unrar-toolchain:local bash /src/scripts/check-container.sh
