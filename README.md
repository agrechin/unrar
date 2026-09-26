# UnRAR for Apple Silicon

Build, test, sign, notarize, and publish UnRAR entirely in GitHub Actions.
All jobs use GitHub-hosted runners; no local build tools or self-hosted machines
are required. This is an independent build and distribution, not an official
RARLAB release.

The target is **macOS 12 or later, Apple Silicon only**. Intel is not supported.
CI verifies the linked minimum OS and runs extraction tests on current macOS;
compatibility still needs testing on an actual macOS 12 machine.

After the first signed release has been published:

```sh
brew install --cask agrechin/tap/unrar
unrar x archive.rar
```

## Operate from GitHub

Use the repository's [Actions tab](https://github.com/agrechin/unrar/actions):

| Workflow | Trigger | Result |
| --- | --- | --- |
| CI | Pull request, push to `main`, or **Run workflow** | Linux checks plus a native arm64 build and extraction tests on macOS; an unsigned artifact for inspection |
| Update upstream | **Run workflow** on `main`, with a stable RARLAB archive URL and expected SHA-256 | Imports the source, opens a PR, and explicitly dispatches CI on its branch |
| Prepare release | **Run workflow** on `main`, with a full commit SHA from passing CI on `main` | Verifies stable source and both CI jobs, creates the version tag, and dispatches Release |
| Release | Version tag push or dispatch on that tag | Checks, builds, signs, notarizes, tests the DMG, publishes a GitHub release, and updates Homebrew |

Normal pushes and upstream-update PRs do not publish releases. Review and merge
the update, wait for CI on `main`, and then use **Prepare release**. See the
[upgrade guide](docs/upgrading.md) for the browser-only procedure and recovery.

## Build design

Linux checks run on `ubuntu-24.04` in the repository's Docker image: source
verification, ShellCheck, actionlint, Python tests, cask syntax, Linux compilation,
and RAR4/RAR5 extraction tests. The image uses digest-pinned Ubuntu 26.04 and LLVM
21; packages are resolved when the image is built.

The macOS job uses GitHub's `macos-26` arm64 runner, explicitly selects **Xcode
26.5 and SDK 26.5**, and builds natively with Apple Clang and the upstream
makefile. It does not use Docker or copy the Apple SDK. The same build script
and smoke tests run in CI and Release. A missing selected toolchain fails the
build instead of silently selecting another version.

`build-info.json` records the upstream archive and source checksums, actual SDK,
compiler, Xcode and runner image versions, linked minimum OS, and unsigned binary
checksum. Hosted images receive updates, so builds are not claimed to be
byte-for-byte reproducible. Release validation rejects changed source or binary
bytes before signing. The complete RARLAB source and licenses stay unmodified
in `vendor/unrar/`.

Repository scripts are CI entrypoints. Contributors who already have the tools
can optionally run `bash scripts/check.sh` with Docker, or `bash scripts/build.sh`
on Apple Silicon with Xcode 26.5. Neither is required to operate this repository.
Task is only an optional command wrapper.

## One-time GitHub setup

1. Enable GitHub Actions. Under **Settings → Actions → General → Workflow
   permissions**, enable **Allow GitHub Actions to create and approve pull
   requests** so Update upstream can create its PR. Workflows declare their
   required permissions explicitly; the repository default can remain read-only.
2. Protect `main` and require the CI jobs **check** and **macos** before merging.
3. Create an environment named **`release`**, restrict deployment to `v*` tags,
   and configure the secrets below. Required reviewers can be used if desired.

| Secret | Value |
| --- | --- |
| `MACOS_SIGN_P12` | Base64 Developer ID Application certificate and private key, exported as P12 |
| `MACOS_SIGN_PASSWORD` | Password protecting that P12 |
| `MACOS_NOTARY_KEY` | Base64 App Store Connect team API private key (`.p8`) |
| `MACOS_NOTARY_KEY_ID` | API key ID |
| `MACOS_NOTARY_ISSUER_ID` | API issuer ID |
| `HOMEBREW_TAP_TOKEN` | Fine-grained GitHub token with Contents read/write on `agrechin/homebrew-tap` |

Provision these through GitHub's environment secret UI. Existing secrets cannot
be copied back out of another repository; their original values are needed.
There is no runner to register and no `MACOS_SDK_PATH` variable to configure.
Apple credentials are still required for distribution, even though all build
and signing tools run in CI. Never commit SDKs, keys, P12 files, or keychains.

CI runs without signing secrets. Only Release uses the `release` environment.
The signing script imports the P12 into a temporary keychain, requires exactly
one valid Developer ID Application identity, and removes temporary key material
on exit. The temporary keychain is added to the runner's search list for signing;
the original search list is restored during cleanup, including on failure.
Hosted runners are discarded after each job.

## Release and recovery

Prepare release accepts only a full SHA reachable from `main` whose latest push
CI run passed both Linux and macOS jobs. It derives the tag from `version.hpp`,
requires `RARVER_BETA=0`, and never moves an existing tag. A matching tag can be
reused if dispatch failed before a release was created. GitHub's built-in token
does not trigger push workflows when it creates a tag, so preparation explicitly
dispatches Release on that tag.

Release runs Linux checks, builds and tests the unsigned arm64 binary, signs it
with hardened runtime and a secure timestamp, creates and signs a DMG, and
submits it to Apple. It requires **Accepted**, staples and validates the ticket,
runs Gatekeeper assessment, mounts the DMG, and tests its packaged binary.
The final DMG checksum is used for the Homebrew cask. The publisher verifies
downloaded release bytes before updating only `Casks/unrar.rb` in the tap.

The cask uses Homebrew's `binary` artifact with arm64 and minimum-macOS
constraints. It never strips quarantine or bypasses Gatekeeper. DMGs support
stapling; standalone command-line executables do not carry a stapled ticket.

If publication succeeds but the tap update fails, use **Re-run failed jobs** in
the original Release run. This reuses its signed artifact. Never rerun all jobs
or Prepare release to replace published bytes: rebuilding/signing produces a
different DMG. Signed workflow artifacts are retained for 14 days.

If preparation creates a tag but dispatch fails, retry preparation for the same
commit, or manually run **Release**, selecting the tag both in the **Use workflow
from** selector and the `tag` input. Do not select `main` for Release. A failed or
timed-out notarization cannot publish; inspect the submission ID and Apple log
before retrying. Signing and publication reject local execution.

An unsigned CI pass does not verify Apple credentials or prove that a signed
release is ready. Validate signing and notarization in a real Release run.

## Upstream and licenses

[`upstream.json`](upstream.json) is the authoritative record of the current
stable source version, exact RARLAB archive URL, archive SHA-256, and every
vendored file checksum. Do not infer the application version from the archive
filename: the imported `unrarsrc-7.2.7.tar.gz`, for example, declares UnRAR 7.23.
[RARLAB's general download page](https://www.rarlab.com/rar_add.htm) can point to
a beta; imports use an exact versioned stable source archive instead.

UnRAR is source-available freeware governed by
[`license.txt`](vendor/unrar/license.txt), including its restriction on developing
a RAR-compatible archiver or recreating RAR compression. It is not MIT-licensed.
See [`acknow.txt`](vendor/unrar/acknow.txt) for included components. Extraction
fixtures retain their separate libarchive license.

References: [GitHub macOS runner software](https://github.com/actions/runner-images/blob/main/images/macos/macos-26-arm64-Readme.md),
[Apple notarization](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow),
[Homebrew Cask](https://docs.brew.sh/Cask-Cookbook).
