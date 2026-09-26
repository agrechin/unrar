#!/usr/bin/env bash
set -euo pipefail
python3 /src/scripts/release.py verify-source
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp /src/*.cpp /src/*.hpp /src/makefile "$work/"
cd "$work"
# Use SDK libc++ headers explicitly: the container's Linux headers are wrong.
make -j"$(nproc)" \
  CXX='clang++ --target=arm64-apple-macos12.0 -isysroot /sdk -stdlib=libc++ -nostdinc++ -isystem /sdk/usr/include/c++/v1' \
  LDFLAGS='-fuse-ld=lld -pthread' STRIP='llvm-strip'
install -m 755 unrar /out/unrar
cp /src/license.txt /src/acknow.txt /out/
python3 /src/scripts/release.py build-info /out/build-info.json
