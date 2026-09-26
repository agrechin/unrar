#!/usr/bin/env bash
set -euo pipefail
cd /src
python3 scripts/release.py verify-source
shellcheck scripts/*.sh
actionlint -color .github/workflows/*.yml
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/release.py version
python3 - <<'PY' > /tmp/unrar.rb
from scripts.release import cask_text, version
print(cask_text(version(), 'a' * 64), end='')
PY
ruby -c /tmp/unrar.rb
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp /src/*.cpp /src/*.hpp /src/makefile "$work/"
make -s -C "$work" -j"$(nproc)" CXX=clang++ STRIP=llvm-strip
python3 scripts/smoke.py "$work/unrar"
