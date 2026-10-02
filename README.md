# UnRAR for Apple Silicon — signed and notarized

Extract RAR archives from the terminal with RARLAB's free `unrar` utility.
This independent distribution builds stable, unmodified UnRAR source for Apple
Silicon, signs it with an Apple Developer ID, and distributes it in an
Apple-notarized DMG. Install a prebuilt binary through Homebrew without compiling
UnRAR yourself.

This is an independent build and distribution, not an official RARLAB release.

## Install

With [Homebrew](https://brew.sh/) installed:

```sh
brew install --cask agrechin/tap/unrar
unrar x archive.rar
```

**Apple Silicon only.** The binary targets macOS 12 or later; Intel is not
supported. CI verifies the linked minimum OS and runs extraction tests on
current macOS. Compatibility still needs testing on an actual macOS 12 machine.

To update:

```sh
brew update
brew upgrade --cask agrechin/tap/unrar
```

The signed DMG and SHA-256 checksums are also available from
[GitHub Releases](https://github.com/agrechin/unrar/releases/latest).

## Why this distribution?

Homebrew [disabled its standard `rar` cask](https://github.com/Homebrew/homebrew-cask/blob/main/Casks/r/rar.rb)
on 1 September 2026 because it fails Gatekeeper checks. That cask provided both
`rar` and `unrar`. This tap provides the UnRAR extractor with Developer ID signing
and Apple notarization, and preserves Homebrew's quarantine handling.

- **Signed and notarized releases.** Both the executable and DMG carry a
  Developer ID signature. The DMG includes a stapled Apple notarization ticket
  and is checked with Gatekeeper before publication. Installation does not
  require removing quarantine or disabling Gatekeeper.
- **The familiar UnRAR CLI.** Use RARLAB's command syntax and extraction engine
  in terminal sessions and existing scripts. The complete stable upstream source
  and its licenses are preserved without modification.
- **Prebuilt and managed by Homebrew.** Install and update through the tap;
  no local UnRAR build or Xcode installation is needed.
- **Traceable builds.** Public [build and release workflows](https://github.com/agrechin/unrar/actions),
  source checksums, packaged build metadata, and release checksums make the
  source and toolchain inspectable. CI tests RAR4 and RAR5 extraction.

[RARLAB also provides native Apple Silicon binaries](https://www.rarlab.com/download.htm).
For its macOS ARM 7.23 download, the `unrar` executable has an ad-hoc signature,
without a Developer ID identity; this was checked on 3 October 2026. The benefit
here is the signed, notarized packaging and Homebrew distribution.

## Usage

```sh
unrar l archive.rar   # List contents
unrar t archive.rar   # Test archive integrity
unrar x archive.rar   # Extract, preserving directories
```

This package provides `unrar` only. It does not create RAR archives, install the
`rar` compressor, or provide a graphical interface.

## Verify a release

Releases are signed as **Developer ID Application: Andrei Grechin (49996Q6458)**.
The Team ID is **`49996Q6458`**.

Download the DMG and `checksums.txt` from the same
[release](https://github.com/agrechin/unrar/releases). In the download directory,
run the following, using the filename of the DMG you downloaded:

```sh
dmg="unrar_7.23.0_darwin_arm64.dmg"
shasum -a 256 -c checksums.txt
codesign --verify --strict --verbose=2 "$dmg"
codesign --display --verbose=2 "$dmg"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
```

Confirm that the checksum and signature checks succeed, the displayed signing
identity matches the one above, and Gatekeeper reports `accepted` with
`source=Notarized Developer ID`. A matching checksum verifies the downloaded
bytes against the release manifest; it does not independently establish trust
in the publisher.

The DMG also contains `build-info.json`, which records the upstream archive and
source checksums, compiler, Xcode, SDK, runner image, minimum macOS target, and
the binary checksum **before signing**. Hosted runner images change, so builds
are not claimed to be byte-for-byte reproducible.

## Alternatives

- [carlocab's Homebrew formula](https://github.com/carlocab/homebrew-personal/blob/master/Formula/unrar.rb)
  is another way to install UnRAR, with bottles for several platforms.
- [MacPorts](https://ports.macports.org/port/unrar/) packages UnRAR for users of
  that package manager.
- [Homebrew's `unar`](https://formulae.brew.sh/formula/unar) offers archive
  extraction with a different command-line interface, if you do not need
  RARLAB's `unrar` command and options.

## Source and licenses

[`upstream.json`](upstream.json) records the stable source version, exact RARLAB
archive URL, archive SHA-256, and every vendored file checksum. The upstream
source is kept in [`vendor/unrar/`](vendor/unrar/).

UnRAR is source-available freeware under
[RARLAB's license](vendor/unrar/license.txt), including its restriction on
developing a RAR-compatible archiver or recreating RAR compression. It is not
MIT-licensed. See [the acknowledgements](vendor/unrar/acknow.txt) for included
components. Repository tooling and documentation use the [MIT license](LICENSE);
extraction fixtures retain their [separate libarchive license](tests/fixtures/README.md).

## Maintainers and contributors

See the [maintainer guide](docs/maintaining.md) for build design, GitHub setup,
signing, and release protections. The [upgrade guide](docs/upgrading.md) explains
how to import stable upstream source, publish from GitHub Actions, and recover
from a failed release.
