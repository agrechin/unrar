#!/usr/bin/env bash
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${GITHUB_REPOSITORY:-} == agrechin/unrar &&
   ${GITHUB_WORKFLOW:-} == 'Update upstream' && ${GITHUB_REF:-} == refs/heads/main ]] || {
  echo 'Run Update upstream from main in this repository GitHub Actions.' >&2; exit 1;
}
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
# Validate before downloading, and never interpolate UI inputs into shell code.
python3 - <<'PY'
import os, re
if not re.fullmatch(r'https://www\.rarlab\.com/rar/unrarsrc-[0-9.]+\.tar\.gz', os.environ['UPSTREAM_URL']):
    raise SystemExit('Use an exact versioned RARLAB source URL.')
if not re.fullmatch(r'[a-f0-9]{64}', os.environ['UPSTREAM_SHA256']):
    raise SystemExit('Expected a lowercase SHA-256 checksum.')
PY
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
curl --fail --location --proto '=https' --proto-redir '=https' \
  --output "$temporary/source.tar.gz" "$UPSTREAM_URL"
python3 scripts/import-upstream.py "$temporary/source.tar.gz" \
  --url "$UPSTREAM_URL" --sha256 "$UPSTREAM_SHA256"
if git diff --quiet -- vendor/unrar upstream.json; then
  echo 'This upstream snapshot is already imported.'
  exit 0
fi
version=$(python3 scripts/release.py version)
branch="codex/update-unrar-${version}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
git switch -c "$branch"
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -- vendor/unrar upstream.json
git commit -m "chore: update UnRAR to $version"
git push origin "$branch"
cat > "$temporary/body.md" <<EOF
Import stable UnRAR $version from the versioned RARLAB source archive.

Source: $UPSTREAM_URL
Archive SHA-256: $UPSTREAM_SHA256

The importer preserves upstream file bytes and rejects beta source, unexpected
archive paths, and checksum mismatches. Review source and license changes.
The CI workflow is dispatched explicitly for this branch and must pass before merge.
EOF
gh pr create --repo agrechin/unrar --base main --head "$branch" \
  --title "chore: update UnRAR to $version" --body-file "$temporary/body.md"
# Events created by GITHUB_TOKEN do not trigger push/pull_request workflows.
gh workflow run ci.yml --repo agrechin/unrar --ref "$branch"
