#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
image=unrar-toolchain:local

docker build --tag "$image" --file "$root/docker/Dockerfile" "$root"
if [[ ${1:-} == --tools-only ]]; then
  exit 0
fi
[[ $(uname -s) == Darwin ]] || { echo 'Build on a Mac with Xcode Command Line Tools and Docker.' >&2; exit 1; }
sdk=${MACOS_SDK_PATH:-$(xcrun --sdk macosx26.5 --show-sdk-path)}
sdk=$(cd "$sdk" && pwd -P)
[[ -f "$sdk/SDKSettings.json" ]] || { echo 'Invalid macOS SDK.' >&2; exit 1; }
mkdir -p "$root/.build/macos"
# Docker Desktop does not share /Library by default. Stage the SDK only in
# ignored local build storage, outside the Docker build context.
sdk_stage=$(mktemp -d "$root/.build/sdk.XXXXXX")
trap 'rm -rf "$sdk_stage"' EXIT
ditto --noextattr --norsrc "$sdk" "$sdk_stage/MacOSX.sdk"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$root,target=/src,readonly" \
  --mount "type=bind,source=$sdk_stage/MacOSX.sdk,target=/sdk,readonly" \
  --mount "type=bind,source=$root/.build/macos,target=/out" \
  "$image" bash /src/scripts/build-container.sh
