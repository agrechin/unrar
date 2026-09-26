# Upgrade and release from GitHub

No local build tools are required. Each checkout contains one complete upstream
snapshot in `vendor/unrar/`; older versions remain in Git tags and releases.
Complete the [one-time GitHub setup](../README.md#one-time-github-setup) first.

## 1. Import a stable upstream archive

Find the exact versioned UnRAR **source** archive on
[RARLAB](https://www.rarlab.com/rar_add.htm). The general source link may point to
a beta, which this repository will reject. Obtain the expected archive SHA-256
and compare it with an official checksum if one is available. Otherwise, review
the source provenance and record its checksum as a fingerprint; a checksum
calculated from a download alone does not authenticate its origin.

In **Actions → Update upstream → Run workflow**:

- Select `main` in **Use workflow from**.
- Enter the exact `https://www.rarlab.com/rar/unrarsrc-<version>.tar.gz` URL.
- Enter the expected SHA-256 as 64 lowercase hexadecimal characters.

The workflow downloads the archive, verifies its checksum, and invokes the
existing importer. The importer rejects beta source, links, unexpected paths,
duplicate entries, and modified existing source. It replaces the complete
snapshot without changing upstream file bytes and regenerates `upstream.json`.
The archive filename does not necessarily match `version.hpp`; the latter
defines the application version and release tag.

If the snapshot changed, the workflow commits only `vendor/unrar/` and
`upstream.json` on a new `codex/` branch and opens a pull request. It explicitly
dispatches CI because PRs created with `GITHUB_TOKEN` do not automatically trigger
pull-request workflows. No signing credentials are available to this CI run.

If PR creation fails, check **Settings → Actions → General → Workflow
permissions → Allow GitHub Actions to create and approve pull requests**. The
branch remains available; fix the setting and rerun the update, or open its PR
in the browser and manually run CI on that branch. If only CI dispatch fails,
manually run **CI** with the PR branch selected.

## 2. Review and merge

Review the source, license, acknowledgement, version, and manifest changes in
the PR. Check **check** and **macos** results, including extraction tests on both
platforms. If upstream changes its layout or build system, update the tooling
explicitly before merging. Never edit upstream `version.hpp` to invent a
version or turn a beta into stable source.

Merge according to repository history policy. Then wait for **CI on `main`** to
pass and copy that run's full 40-character commit SHA. A successful PR build
alone is insufficient for release preparation. Normal pushes do not publish.

## 3. Prepare and follow the release

In **Actions → Prepare release → Run workflow**, select `main` and enter the
tested commit SHA. Preparation checks that the commit belongs to `main`, that
its latest push CI passed both required jobs, and that its upstream source is
stable and matches the manifest. It creates `v<version>` and starts **Release**
on that tag. It refuses to move a tag or start over when a release already exists.

Follow the separately dispatched **Release** run in Actions. Preparation success
means the release was dispatched, not that publication has finished. Release
uses the tag-scoped `release` environment, performs signing and notarization on
a hosted Apple Silicon runner, and publishes from hosted Ubuntu.

After Release succeeds, verify the GitHub release and the updated
[`Casks/unrar.rb`](https://github.com/agrechin/homebrew-tap/blob/main/Casks/unrar.rb).
Users can then run `brew update` and `brew upgrade --cask agrechin/tap/unrar`.

## Recovery and older versions

- Tag created but dispatch failed: rerun preparation for the same SHA, or
  manually run Release with the tag selected as both workflow ref and input.
- Signing/notarization failed before publication: inspect the failing step and
  Apple submission log, correct the cause, and rerun failed jobs.
- Publication/tap update failed: rerun **only failed jobs in the original Release
  run**, preserving its original signed artifact. Never rebuild an already
  published release. Artifacts expire after 14 days.

Each tag has its own GitHub release, but the Homebrew tap exposes one `unrar`
cask and one installed command. It does not provide a version selector or
parallel installs. Download older releases directly rather than republishing
them: rerunning an old publisher after a newer release can move the cask back
to the older version. Published assets and existing tags must not be replaced.
