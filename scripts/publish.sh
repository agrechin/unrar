#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tag=${1:?Usage: publish.sh vVERSION}
version=$(python3 "$root/scripts/release.py" check-tag "$tag")
: "${GH_TOKEN:?GitHub release token is required}"
: "${HOMEBREW_TAP_TOKEN:?Homebrew tap token is required}"
dist="$root/.build/release"
artifact="unrar_${version}_darwin_arm64.dmg"
repo=agrechin/unrar
python3 - "$dist" <<'PY'
import json, sys
from pathlib import Path
directory = Path(sys.argv[1])
if json.loads((directory / 'notarization.json').read_text()).get('status') != 'Accepted':
    raise SystemExit('No accepted notarization receipt; refusing publication')
PY
(cd "$dist" && shasum -a 256 -c checksums.txt)
# Derive the cask again from these exact final bytes, not from downloaded input.
python3 "$root/scripts/release.py" package-metadata "$tag" "$dist"
ruby -c "$dist/unrar.rb"
[[ $(gh repo view "$repo" --json visibility --jq .visibility) == PUBLIC ]] || {
  echo 'Homebrew release assets must be publicly downloadable.' >&2; exit 1;
}
temp=$(mktemp -d)
trap 'rm -rf "$temp"' EXIT
cat > "$temp/notes.md" <<EOF
UnRAR $version for Apple Silicon (macOS 12 or later), built from the source in this tag.

The DMG and executable are Developer ID signed; the DMG is notarized and stapled.

Install after the Homebrew tap update completes:

\`\`\`sh
brew install --cask agrechin/tap/unrar
\`\`\`

UnRAR is source-available freeware under RARLAB's license. The archive includes
the original license and acknowledgements. Source: https://github.com/$repo/tree/$tag
EOF
if ! gh release view "$tag" --repo "$repo" --json isDraft > "$temp/release.json"; then
  prerelease=()
  [[ $version != *-beta.* ]] || prerelease=(--prerelease)
  gh release create "$tag" --repo "$repo" --verify-tag --draft "${prerelease[@]}" \
    --title "UnRAR $version (Apple Silicon)" --notes-file "$temp/notes.md"
  gh release view "$tag" --repo "$repo" --json isDraft > "$temp/release.json"
fi
is_draft=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["isDraft"])' "$temp/release.json")
if [[ $is_draft == True ]]; then
  gh release upload "$tag" --repo "$repo" --clobber "$dist/$artifact" "$dist/checksums.txt" "$dist/unrar.rb"
  gh release edit "$tag" --repo "$repo" --draft=false
fi
# Reruns may finish the tap update, but never replace already-published bytes.
gh release download "$tag" --repo "$repo" --pattern "$artifact" --dir "$temp"
cmp "$dist/$artifact" "$temp/$artifact" || {
  echo 'Published artifact differs. Restore the original workflow artifact; do not replace a release.' >&2; exit 1;
}
python3 "$root/scripts/publish-tap.py" "$tag" "$dist/unrar.rb"
