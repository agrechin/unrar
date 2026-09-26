#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tag=${1:?Usage: verify-release.sh vVERSION}
[[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Invalid stable release tag.' >&2; exit 1; }
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || {
  echo 'Release verification requires an Apple Silicon Mac.' >&2; exit 1;
}
dist="$root/.build/release"
dmg="$dist/unrar_${tag#v}_darwin_arm64.dmg"
[[ -f $dmg && ! -L $dmg ]] || { echo 'Signed disk image is missing or is a symlink.' >&2; exit 1; }
(cd "$dist" && shasum -a 256 -c checksums.txt)
codesign --verify --strict --verbose=2 "$dmg"
xcrun stapler validate "$dmg"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
private=$(mktemp -d "${TMPDIR:-/tmp}/unrar-verify.XXXXXX")
mountpoint="$private/mounted"
cleanup() {
  local result=$?
  trap - EXIT
  if mount | grep -Fq " on $mountpoint "; then
    hdiutil detach -quiet "$mountpoint" || result=1
  fi
  rm -rf "$private"
  exit "$result"
}
trap cleanup EXIT
mkdir "$mountpoint"
hdiutil attach -quiet -readonly -nobrowse -mountpoint "$mountpoint" "$dmg"
codesign --verify --strict --verbose=2 "$mountpoint/unrar"
python3 "$root/scripts/smoke.py" "$mountpoint/unrar"
