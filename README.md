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
| Release | Dispatch on `main`, with an existing version tag and its full commit SHA | Authorizes the SHA, checks, builds, signs, notarizes, tests the DMG, publishes a GitHub release, and updates Homebrew |

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
2. Protect `main`: require a reviewed pull request and the CI jobs **check** and
   **macos** for contributors, and block force pushes and deletion. Administrators
   who can change these controls are trusted release operators.
3. Create an environment named **`release`**. Select **Selected branches and
   tags** with exactly one **Branch** rule named **`main`** and no tag rules.
   Keep signing, publication, and tag-creation credentials exclusively in this
   environment, never in repository or organization secrets. Required reviewers
   may add another approval gate. Disable administrator bypass of environment
   protections.
4. Import both JSON files from [`.github/rulesets`](.github/rulesets) under
   **Settings → Rules → Rulesets → Import a ruleset**. Activate both for `v*`:
   **Release tag creation** permits only repository administrators; **Immutable
   release tags** blocks updates and deletion with an empty bypass list.
   Separate rulesets ensure the tag creator cannot also move or delete tags.
   These files are templates; committing them does not activate GitHub rules.
5. Configure the environment secrets below. For tag creation, use a fine-grained
   token owned by a repository administrator, scoped only to this repository
   with **Contents: read/write**. Do not grant the general GitHub Actions app a
   tag-rule bypass: its token is also available to other workflows.

| Secret | Value |
| --- | --- |
| `RELEASE_TAG_TOKEN` | Administrator's fine-grained token described above; used only by Prepare release to create a protected tag |
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

CI runs without signing secrets. Prepare release uses the `release` environment
for tag creation; Release uses it for signing and publication. Both workflows
run from `main`. Environment ref restrictions are essential: guards in a YAML
file cannot stop an attacker who can replace that file on a tag or branch.
The signing script imports the P12 into a temporary keychain, requires exactly
one valid Developer ID Application identity, and removes temporary key material
on exit. The temporary keychain is added to the runner's search list for signing;
the original search list is restored during cleanup, including on failure.
Hosted runners are discarded after each job.

## Release and recovery

Prepare release accepts only a full SHA reachable from `main` whose latest push
CI run passed both Linux and macOS jobs. It derives the tag from `version.hpp`,
requires `RARVER_BETA=0`, and never moves an existing tag. A matching tag can be
reused if dispatch failed before a release was created. Preparation uses the
dedicated tag token only for tag creation and explicitly dispatches Release on
`main` with the tag and full SHA. Tag pushes do not start a release.

Release independently checks the tag's target, ancestry in the workflow's
immutable `main` snapshot, stable source, and successful main-push CI before
executing any candidate tooling. Admission uses code from the workflow's own
SHA, with no release environment or signing credentials. Linux checks use the
admitted SHA without release secrets. The native build runs protected-main
controller scripts against the admitted source on a runner without secrets.
Signing and publication use protected-main controller scripts and inspect the
candidate checkout as data. No job resolves the tag for code. The publisher
rechecks the tag-to-SHA mapping. Tag immutability closes the remaining race between that
check and publication.

Release runs Linux checks, builds and tests the unsigned arm64 binary on a
credential-free runner, then signs the uploaded artifact on a fresh runner with
hardened runtime and a secure timestamp. It creates and signs a DMG, submits it
to Apple, requires **Accepted**, and staples the ticket. A separate runner without
release secrets validates Gatekeeper, mounts the DMG, and tests its binary before
publication.
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
commit, or manually run **Release**, selecting `main` in **Use workflow from**,
and entering the version tag and its original full commit SHA. A failed or
timed-out notarization cannot publish; inspect the submission ID and Apple log
before retrying. Signing and publication reject local execution.

An unsigned CI pass does not verify Apple credentials or prove that a signed
release is ready. Validate signing and notarization in a real Release run.

When adopting this policy, update the live environment and rulesets before
allowing another release. Cancel obsolete queued tag-based runs and start a new
main-based run only for unpublished source containing this policy. Existing
published bytes stay intact; an old run must not regain tag access to secrets.
Confirm the live settings separately from the repository templates. See
[GitHub environment ref rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
and [ruleset controls](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).

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
