#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
source_root=${UNRAR_SOURCE_ROOT:-$root}
[[ $# == 0 ]] || { echo 'Usage: build.sh' >&2; exit 1; }
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || {
  echo 'Native build requires an Apple Silicon macOS runner.' >&2; exit 1;
}
# Use the same explicitly selected toolchain in validation and release jobs.
export DEVELOPER_DIR=/Applications/Xcode_26.5.app/Contents/Developer
sdk=$(xcrun --sdk macosx26.5 --show-sdk-path)
[[ $(xcrun --sdk macosx26.5 --show-sdk-version) == 26.5 ]] || {
  echo 'Expected macOS SDK 26.5.' >&2; exit 1;
}
python3 "$root/scripts/release.py" verify-source
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp -R "$source_root/vendor/unrar/." "$work/"
# Keep architecture, SDK, and minimum OS on both compile and link commands.
make -C "$work" -j"$(sysctl -n hw.logicalcpu)" \
  CXX="xcrun --sdk macosx26.5 clang++ -arch arm64 -isysroot $sdk -mmacosx-version-min=12.0" \
  STRIP='xcrun strip'
out="$root/.build/macos"
mkdir -p "$out"
install -m 755 "$work/unrar" "$out/unrar"
cp "$source_root/vendor/unrar/license.txt" "$source_root/vendor/unrar/acknow.txt" "$out/"
[[ $(lipo -archs "$out/unrar") == arm64 ]] || { echo 'Expected arm64 binary.' >&2; exit 1; }
python3 "$root/scripts/release.py" build-info "$out/build-info.json"
python3 "$root/scripts/smoke.py" "$out/unrar"
