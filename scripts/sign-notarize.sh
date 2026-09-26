#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
version=$(python3 "$root/scripts/release.py" preflight sign "${1:?Usage: sign-notarize.sh vVERSION}")
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || {
  echo 'Signing and release smoke tests require an Apple Silicon Mac.' >&2; exit 1;
}
python3 "$root/scripts/release.py" validate-build "$root/.build/macos"
[[ $(lipo -archs "$root/.build/macos/unrar") == arm64 ]] || { echo 'Expected arm64 binary.' >&2; exit 1; }
python3 "$root/scripts/smoke.py" "$root/.build/macos/unrar"

umask 077
private=$(mktemp -d "${TMPDIR:-/tmp}/unrar-sign.XXXXXX")
keychain="$private/signing.keychain-db"
mountpoint="$private/mounted"
cleanup() {
  if mount | grep -Fq " on $mountpoint "; then
    hdiutil detach -quiet "$mountpoint" || true
  fi
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  rm -rf "$private"
}
trap cleanup EXIT
export UNRAR_PRIVATE_DIR="$private"
python3 - <<'PY'
import base64, os
from pathlib import Path
directory = Path(os.environ['UNRAR_PRIVATE_DIR'])
for variable, filename in [('MACOS_SIGN_P12', 'certificate.p12'), ('MACOS_NOTARY_KEY', 'notary.p8')]:
    value = ''.join(os.environ[variable].split())
    (directory / filename).write_bytes(base64.b64decode(value, validate=True))
PY
keychain_password=$(openssl rand -hex 32)
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 7200 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$private/certificate.p12" -k "$keychain" -P "$MACOS_SIGN_PASSWORD" -T /usr/bin/codesign >/dev/null
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$keychain_password" "$keychain" >/dev/null
identity=$(security find-identity -v -p codesigning "$keychain" | awk '/"Developer ID Application:/ {print $2}')
[[ "$identity" =~ ^[A-Fa-f0-9]{40}$ ]] || { echo 'P12 must contain exactly one valid Developer ID Application identity.' >&2; exit 1; }

dist="$root/.build/release"
mkdir -p "$dist"
# A unique stage prevents a failed retry from reusing a prior signed package.
stage="$private/payload"
mkdir "$stage"
cp "$root/.build/macos/"{unrar,license.txt,acknow.txt,build-info.json} "$stage/"
chmod 755 "$stage"
chmod 644 "$stage/"{license.txt,acknow.txt,build-info.json}
chmod 755 "$stage/unrar"
codesign --force --sign "$identity" --keychain "$keychain" --timestamp \
  --options runtime --identifier com.github.agrechin.unrar "$stage/unrar"
codesign --verify --strict --verbose=2 "$stage/unrar"
python3 "$root/scripts/smoke.py" "$stage/unrar"
dmg="$dist/unrar_${version}_darwin_arm64.dmg"
hdiutil create -quiet -ov -format UDZO -fs HFS+ -volname UnRAR -srcfolder "$stage" "$dmg"
codesign --sign "$identity" --keychain "$keychain" --timestamp "$dmg"
codesign --verify --strict --verbose=2 "$dmg"

notary_args=(--key "$private/notary.p8" --key-id "$MACOS_NOTARY_KEY_ID" --issuer "$MACOS_NOTARY_ISSUER_ID")
submission="$private/submission.json"
result=0
xcrun notarytool submit "$dmg" "${notary_args[@]}" --wait --timeout 60m --output-format json > "$submission" || result=$?
cat "$submission"
submission_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$submission")
xcrun notarytool log "$submission_id" "${notary_args[@]}" "$dist/notarization-log.json"
[[ $result == 0 ]] || { echo 'Notarization failed or timed out. See the submission ID and log.' >&2; exit "$result"; }
python3 - "$submission" <<'PY'
import json, sys
response = json.load(open(sys.argv[1]))
if response.get('status') != 'Accepted':
    raise SystemExit('Apple did not accept the notarization; publication is blocked.')
PY
xcrun stapler staple "$dmg"
xcrun stapler validate "$dmg"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
mkdir "$mountpoint"
hdiutil attach -quiet -readonly -nobrowse -mountpoint "$mountpoint" "$dmg"
codesign --verify --strict --verbose=2 "$mountpoint/unrar"
python3 "$root/scripts/smoke.py" "$mountpoint/unrar"
hdiutil detach -quiet "$mountpoint"
cp "$submission" "$dist/notarization.json"
python3 "$root/scripts/release.py" package-metadata "v$version" "$dist"
echo "Signed, notarized, and stapled: $dmg"
