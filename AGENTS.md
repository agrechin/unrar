# Repository guidance

- Keep RARLAB source and its license intact in `vendor/unrar/`; scope build-tool
  changes to tooling.
- Import upstream upgrades exactly from a stable RARLAB archive and update its
  URL, archive checksum, and file checksums in `upstream.json` with
  `scripts/import-upstream.py`; see `docs/upgrading.md`.
- All checks, updates, builds, and releases must be operable in GitHub-hosted CI;
  do not require local tooling installation or a self-hosted runner.
- CI must pass both `check` (Docker on Ubuntu) and `macos` (native build and smoke
  tests). Keep `scripts/check.sh` and `scripts/build.sh` as the shared entrypoints.
- Builds target macOS arm64 only, using Xcode 26.5 and SDK 26.5 explicitly.
  Fail if that toolchain is unavailable; do not silently switch SDKs.
- Never commit or publish Apple SDKs, private keys, P12 files, or keychains.
- Release signing and notarization must fail closed; never strip quarantine.
- Pull-request CI must never receive signing or publication credentials.
- Release only stable source (`RARVER_BETA=0`); keep tags aligned with `version.hpp`.
- Signing and publishing run only in the GitHub Release workflow dispatched from
  protected main for an authorized tag and immutable commit SHA. Never execute
  admission code from the candidate tag or resolve tags again for job checkouts.
- Restrict the release environment to the main branch. Release tag creation is
  restricted; updates/deletions have no ruleset bypass. Keep tag credentials in
  the release environment and separate from the built-in workflow token.
- Prepare release requires a main-branch commit with passing Linux and macOS CI.
  GITHUB_TOKEN-created tags/PRs need explicit workflow dispatch to trigger CI.
- Preserve published release bytes. Retry only failed publication jobs to finish
  a tap update using the original signed workflow artifact.
- Use Conventional Commits. Keep single-commit changes on main; rebase branches
  onto the base, never merge the base into a working branch.
