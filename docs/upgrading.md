# Upgrade the upstream UnRAR source

Each checkout contains one upstream version in `vendor/unrar/`. Upgrade by
replacing that **entire snapshot**, including its makefile, license, and
acknowledgements. Keep older versions in Git tags and GitHub Releases, rather
than adding version directories. Repository scripts, tests, and workflows live
outside the snapshot.

## 1. Select and download a stable source archive

For a single upgrade commit, start on `main` with a clean working tree. Find the
official UnRAR **source** archive on
[RARLAB](https://www.rarlab.com/rar_add.htm) and use its exact versioned HTTPS URL.
The general download link may point to a beta. This repository only releases
stable source: `RARVER_BETA` in `version.hpp` must be zero.

Do not infer the application version from the archive filename. For example,
`unrarsrc-7.2.7.tar.gz` contains UnRAR 7.23, which this repository tags `v7.23.0`.
The import command reads the version from the source itself.

Replace the placeholder with the selected archive's URL:

```sh
UPSTREAM_URL='https://www.rarlab.com/rar/unrarsrc-<archive-version>.tar.gz'
mkdir -p .build
curl --fail --location --proto '=https' --proto-redir '=https' \
  "$UPSTREAM_URL" --output .build/upstream.tar.gz
shasum -a 256 .build/upstream.tar.gz
```

Compare the checksum with an official checksum if one is available. Otherwise,
review the archive downloaded over HTTPS from RARLAB and record its SHA-256 as
the import fingerprint; computing a hash alone does not authenticate the source.

## 2. Import the complete snapshot

Set the expected archive checksum, then run:

```sh
UPSTREAM_SHA256='<expected-64-character-sha256>'
python3 scripts/import-upstream.py .build/upstream.tar.gz \
  --url "$UPSTREAM_URL" --sha256 "$UPSTREAM_SHA256"
```

The command checks the archive hash, rejects beta source and unexpected archive
paths or links, and stages the new files before replacing `vendor/unrar/`.
Obsolete files disappear automatically. It regenerates `upstream.json` with the
version, URL, archive checksum, and every upstream file checksum. Manifest
filenames are relative to `vendor/unrar/`. File contents are copied unchanged.
It refuses to discard source files that no longer match the existing manifest.
It does not download, commit, tag, sign, or publish anything.

Review the source and license changes and update README's current version,
file count, archive link/checksum, and release command examples. Do not edit `version.hpp`
to invent a version or turn a beta into a stable release.

```sh
git diff --stat
git diff -- upstream.json README.md
git status --short
python3 scripts/release.py verify-source
python3 scripts/release.py version
```

Use `git status` to include new upstream files in the review; unstaged new files
do not appear in `git diff` yet. If the upstream archive layout or build system
changes, update the import/build tooling explicitly before proceeding.

## 3. Validate and commit

On an Apple Silicon Mac with Docker and SDK 26.5:

```sh
bash scripts/check.sh
bash scripts/build.sh
python3 scripts/smoke.py .build/macos/unrar
```

Review and stage the upstream snapshot, manifest, README, and any required
tooling changes. For an upgrade that only changes the first three:

```sh
git add vendor/unrar upstream.json README.md
git diff --cached --check
git diff --cached --stat
git commit -m "chore: update UnRAR to $(python3 scripts/release.py version)"
git push origin main
```

Wait for the `CI` workflow on that commit to pass before releasing. A normal push
only runs checks; it does not publish a new version.

## 4. Publish a new tag

Once the source commit is reviewed, tested, and on `main`, derive a fresh tag
from the imported source:

```sh
RELEASE_VERSION=$(python3 scripts/release.py version)
git tag -a "v$RELEASE_VERSION" -m "UnRAR $RELEASE_VERSION"
git push origin "v$RELEASE_VERSION"
```

The `Release` workflow builds that tag, signs and notarizes it, publishes a
versioned DMG, and updates `agrechin/homebrew-tap`'s `Casks/unrar.rb` to that
release. Do not move an existing tag or replace published release assets.
For publication recovery, follow the [README](../README.md#publish): rerun only
failed jobs so the original signed artifact is reused.

Users can then update with:

```sh
brew update
brew upgrade --cask agrechin/tap/unrar
```

## What supports multiple versions?

| Component | Current behavior |
| --- | --- |
| Source tree | One upstream version per checkout; Git tags preserve previous snapshots. |
| CI | Tests the version in the checked-out commit. There is no matrix testing older UnRAR versions. |
| Release workflow | Handles successive stable tags with version-specific DMG names and download URLs. Release runs are serialized. |
| GitHub Releases | Separate published releases retain their own assets. Publishing a new tag does not replace earlier release bytes. |
| Homebrew tap | One `unrar` cask, pointing to the last release written by the publisher; one linked `unrar` command. No version selector or parallel installs are configured. |

Publishing an older tag can move the single cask back to that version: the
publisher currently has no version-order check. Do not use an old release run
as a way to install an older version, or rerun its publisher after a newer release.
Existing releases can be downloaded directly without republishing them.

Homebrew supports [separate versioned cask tokens](https://docs.brew.sh/Cask-Cookbook#casks-pinned-to-specific-versions),
but this repository does not generate them. Adding selectable versions would
require separate casks such as `unrar@7.23`; installing them together would also
require distinct [binary targets](https://docs.brew.sh/Cask-Cookbook#stanza-binary)
so they do not compete for `bin/unrar`. That is a separate release-policy change.
