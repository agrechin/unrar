# UnRAR for Apple Silicon

Build RARLAB's stable UnRAR source in Docker, sign and notarize on macOS,
and publish a Homebrew cask in [`agrechin/homebrew-tap`](https://github.com/agrechin/homebrew-tap).
This is an independent build and distribution of UnRAR, not an official RARLAB release.

The current source is **stable 7.23** (`7.23.0` for release tags).
The target is **macOS 12 or later, Apple Silicon only**. Intel is not supported.
The deployment target is checked in the build configuration; the minimum OS
still needs testing on an actual macOS 12 machine.

After the first signed release has been published:

```sh
brew install --cask agrechin/tap/unrar
unrar x archive.rar
```

No release is created by a normal push to `main`.
Signing, notarization, and publication are supported only through the GitHub
`Release` workflow. Local commands provide checks and unsigned builds.

## Build and test

Host prerequisites: an Apple Silicon Mac, Docker with a running local Linux
engine, and Xcode Command Line Tools with **macOS SDK 26.5**. Task is an optional
command wrapper. Compiler, linker, Linux build dependencies, ShellCheck, Ruby,
and Python checks are installed inside Docker.

```sh
bash scripts/check.sh                 # Linux compile, extraction tests, tooling checks
bash scripts/build.sh                 # macOS arm64 cross-build
python3 scripts/smoke.py .build/macos/unrar
```

Equivalent commands: `task check`, `task build`, `task smoke`.
Local commands and CI invoke the same scripts. To run checks and the macOS build
together, use `bash scripts/build.sh --with-checks`; this prepares the Docker
image once. The release workflow uses this combined command.
The output is `.build/macos/unrar`. This local build is not Developer ID signed
or notarized; distribution goes through the release workflow below.

The image uses digest-pinned Ubuntu 26.04 and LLVM 21. Dependency packages are
resolved from Ubuntu when the image is first built; builds are not claimed to
be byte-for-byte reproducible. `build-info.json` records source file checksums,
the SDK, compiler version, deployment target, unsigned executable checksum, and
upstream provenance. Both checks and builds verify the vendored source against
the file checksums in `upstream.json`.

The SDK defaults to `xcrun --sdk macosx26.5 --show-sdk-path`. To select another
compatible, locally installed SDK:

```sh
MACOS_SDK_PATH=/absolute/path/to/MacOSX26.5.sdk bash scripts/build.sh
```

LLVM 21 cannot read the new `arm64e.x1` stubs in SDK 27. Use SDK 26.5 until the
container toolchain has been updated and verified. The build stages a temporary
SDK copy under ignored `.build/` because Docker Desktop does not share `/Library`
by default. It removes that copy on exit. The SDK and source are mounted read-only;
compilation runs without network access. The Docker image contains no Apple SDK,
source, certificates, or private keys. Follow Apple's SDK license terms for the
SDK you install; it is never checked in or uploaded as a CI artifact.

## Release runner and credentials

CI uses GitHub-hosted Linux runners for pull requests. Releases use a dedicated
**self-hosted Apple Silicon Mac** with these runner labels:

```text
self-hosted, macOS, ARM64, unrar-release
```

Install Docker and the SDK on that Mac, register it with `agrechin/unrar`, and
keep its Docker engine running while jobs execute. `codesign`, `security`,
`hdiutil`, `spctl`, `xcrun notarytool`, and Python 3 must be available to the runner
account. Apple's native signing tools run on the host; compilation runs in Docker.
An optional repository variable `MACOS_SDK_PATH` selects the installed SDK path.

Use a dedicated runner account/host for release work. This is a public repository:
never enable pull-request execution on the signing runner. The provided CI workflow
runs PR code only on disposable GitHub-hosted Linux machines.

Create a GitHub environment named **`release`**, restrict it to release tags, and
add these secrets (names match the existing Freda release setup):

| Secret | Value |
| --- | --- |
| `MACOS_SIGN_P12` | Base64 Developer ID Application certificate and private key, exported as P12 |
| `MACOS_SIGN_PASSWORD` | Password protecting that P12 |
| `MACOS_NOTARY_KEY` | Base64 App Store Connect team API private key (`.p8`) |
| `MACOS_NOTARY_KEY_ID` | API key ID |
| `MACOS_NOTARY_ISSUER_ID` | API issuer ID |
| `HOMEBREW_TAP_TOKEN` | Fine-grained GitHub token with Contents read/write on `agrechin/homebrew-tap` |

Use GitHub's secret UI or `gh secret set --env release --repo agrechin/unrar`;
never commit these values. GitHub cannot copy an existing repository secret's
value back out of Freda, so the original values must be provisioned separately.
The built-in GitHub token publishes releases to this public source repository;
no separate `RELEASE_TOKEN` is needed.

The signing script imports the P12 into a temporary keychain, explicitly selects
a valid Developer ID Application identity, and removes the keychain and temporary
private-key files on exit. It does not change the login keychain search list.

## Publish

After the runner and environment secrets are configured, tag the reviewed source:

```sh
git tag -a v7.23.0 -m 'UnRAR 7.23'
git push origin v7.23.0
```

The tag must match `version.hpp`, and `RARVER_BETA` must be zero. The release
preflight rejects beta source even if its tag matches. Casks accept stable
versions only. A manually dispatched `Release` workflow accepts an existing
stable tag as well.

For manual dispatch, select that same tag as the workflow ref so it is allowed
by the release environment's tag policy:

```sh
gh workflow run release.yml --repo agrechin/unrar --ref v7.23.0 -f tag=v7.23.0
```

The release workflow:

1. Validates the release context, stable source, tag, and required credentials
   using the shared preflight in `scripts/release.py`; checks tooling and
   extraction, then builds ARM64 in Docker with one image-preparation step.
2. Checks source and binary hashes to reject stale build output.
3. Signs the executable with hardened runtime and a secure timestamp.
4. Creates and signs a DMG containing `unrar`, the original license,
   acknowledgements, and build metadata.
5. Submits it to Apple with `notarytool`, requires **Accepted**, staples the
   ticket, validates it, and runs Gatekeeper assessment.
6. Mounts the final DMG read-only and tests the packaged binary.
7. Hashes the final stapled DMG and generates the cask using that SHA-256.
8. Publishes the GitHub release, verifies the downloaded release bytes, then
   updates only `Casks/unrar.rb` in the tap with a readback check.

The cask uses Homebrew's `binary` artifact, with ARM64 and minimum-macOS
constraints. It never strips quarantine or bypasses Gatekeeper. DMGs support
stapling; a standalone command-line executable does not carry a stapled ticket.

If publication succeeds but the tap update fails, use **Re-run failed jobs** so
the publisher reuses the same signed artifact. Already-published bytes are never
overwritten. Rebuilding and signing produces a different DMG; do not rerun all
jobs to replace an existing release. Artifacts are retained for 14 days. A failed
or timed-out notarization cannot publish; use its submission ID to investigate
with `notarytool` before retrying.

The signing and publishing entrypoints reject calls outside this repository's
GitHub `Release` workflow on the matching tag. There is no local release command.
Signing/notarization must be validated with real credentials before claiming
that a release is ready.

## Upstream and licenses

The 159 upstream files, including the `makefile` and licenses, are imported
without modification from the official [stable source archive](https://www.rarlab.com/rar/unrarsrc-7.2.7.tar.gz).
The archive filename is `7.2.7`, while its `version.hpp` declares stable **7.23**.
[RARLAB's general source link](https://www.rarlab.com/rar_add.htm) can point to a
beta, so it is not used as an unversioned download source for this repository.

[`upstream.json`](upstream.json) records the URL, archive SHA-256, version, and
individual file checksums. The downloaded archive's verified SHA-256 is:

```text
01d903a7dcf413cb2925696d7796e48e38d471f79bfe7ef3ad2aebf6c12dbefd
```

For an upstream update, select an official stable archive, record its URL and
SHA-256, replace the upstream files exactly (including removing obsolete files),
and regenerate the file checksums in `upstream.json`. Keep repository tooling
outside that import. Re-run the Docker checks, macOS build, and extraction tests.

UnRAR is source-available freeware governed by [`license.txt`](license.txt),
including its restriction on developing a RAR-compatible archiver or recreating
RAR compression. It is not MIT-licensed. See [`acknow.txt`](acknow.txt) for included
components. Extraction fixtures retain their separate libarchive license.

References: [Clang cross-compilation](https://clang.llvm.org/docs/CrossCompilation.html),
[Apple notarization](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow),
[Homebrew Cask](https://docs.brew.sh/Cask-Cookbook).
