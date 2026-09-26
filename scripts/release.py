#!/usr/bin/env python3
"""Version and release metadata; standard library only."""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

# Credentialed jobs run this controller from the workflow's main snapshot while
# reading the authorized candidate checkout as data. Local and CI builds use
# the controller checkout as their source by default.
ROOT = Path(os.environ["UNRAR_SOURCE_ROOT"]).resolve() if os.environ.get("UNRAR_SOURCE_ROOT") else Path(__file__).resolve().parents[1]
SOURCE_DIR = Path("vendor/unrar")
REPOSITORY = "agrechin/unrar"
MIN_MACOS = "12.0"
REQUIRED_SECRETS = {
    "sign": ("MACOS_SIGN_P12", "MACOS_SIGN_PASSWORD", "MACOS_NOTARY_KEY",
             "MACOS_NOTARY_KEY_ID", "MACOS_NOTARY_ISSUER_ID"),
    "publish": ("GH_TOKEN", "HOMEBREW_TAP_TOKEN"),
}


def version(root=ROOT):
    values = dict(re.findall(r"^#define RARVER_(MAJOR|MINOR|BETA)\s+(\d+)$",
                             (root / SOURCE_DIR / "version.hpp").read_text(), re.MULTILINE))
    major, minor, beta = (int(values[k]) for k in ("MAJOR", "MINOR", "BETA"))
    return f"{major}.{minor}.0" + (f"-beta.{beta}" if beta else "")


def check_tag(tag, root=ROOT):
    current = version(root)
    if "-beta." in current:
        raise ValueError("Releases require stable upstream source (RARVER_BETA must be 0)")
    expected = f"v{current}"
    if tag != expected:
        raise ValueError(f"Tag must match version.hpp: expected {expected}, got {tag!r}")
    return tag[1:]


def require_release_ci(tag, env=None, root=ROOT):
    env = os.environ if env is None else env
    expected = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_WORKFLOW": "Release", "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_dispatch", "RELEASE_TAG": tag,
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/release.yml@refs/heads/main",
    }
    if any(env.get(key) != value for key, value in expected.items()):
        raise ValueError("Signing and publishing are supported only by this repository's "
                         "GitHub Release workflow, dispatched from main for an authorized tag")
    commit = env.get("RELEASE_COMMIT", "")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Release requires an authorized immutable commit SHA")
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != commit:
        raise ValueError("Checkout differs from the authorized release commit")


def preflight(stage, tag, root=ROOT, env=None):
    env = os.environ if env is None else env
    require_release_ci(tag, env, root)
    release_version = check_tag(tag, root)
    verify_source(root)
    missing = [name for name in REQUIRED_SECRETS[stage] if not env.get(name)]
    if missing:
        raise ValueError("Required secrets are missing: " + ", ".join(missing))
    return release_version


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_source(root=ROOT):
    provenance = json.loads((root / "upstream.json").read_text())
    if provenance["version"] != version(root):
        raise ValueError("Upstream provenance version does not match version.hpp")
    expected = provenance["files"]
    source = root / SOURCE_DIR
    # This directory contains only the complete, unmodified upstream snapshot.
    extra = {p.name for p in source.iterdir()} - set(expected)
    if extra:
        raise ValueError("Unrecorded upstream source files: " + ", ".join(sorted(extra)))
    for name, checksum in expected.items():
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("Upstream manifest must contain only filenames relative to vendor/unrar")
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Upstream source must be a regular file: {name}")
        if sha256(path) != checksum:
            raise ValueError(f"Upstream source checksum mismatch: {name}")


def cask_text(release_version, checksum):
    if not re.fullmatch(r"\d+\.\d+\.\d+", release_version):
        raise ValueError("Casks require a stable release version")
    if not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid SHA-256")
    return f'''cask "unrar" do
  version "{release_version}"
  sha256 "{checksum}"

  url "https://github.com/{REPOSITORY}/releases/download/v#{{version}}/unrar_#{{version}}_darwin_arm64.dmg"
  name "UnRAR"
  desc "Extract RAR archives from the command line"
  homepage "https://github.com/{REPOSITORY}"

  depends_on arch: :arm64
  depends_on macos: ">= :monterey"

  binary "unrar"
end
'''


def build_info(output, root=ROOT):
    verify_source(root)
    provenance = json.loads((root / "upstream.json").read_text())
    source = root / SOURCE_DIR
    def xcrun(*args):
        return subprocess.check_output(["xcrun", "--sdk", "macosx26.5", *args], text=True).strip()

    # Read the actual linked deployment target, not just the intended flags.
    load_commands = subprocess.check_output(["otool", "-l", str(output.parent / "unrar")], text=True)
    minimum = re.search(r"\bminos\s+(\S+)", load_commands)
    if not minimum or minimum[1] != MIN_MACOS:
        raise ValueError(f"Expected linked minimum macOS {MIN_MACOS}")
    data = {
        "version": version(root), "architecture": "arm64", "minimum_macos": MIN_MACOS,
        "sdk": xcrun("--show-sdk-version"),
        "compiler": xcrun("clang++", "--version"),
        "xcode": subprocess.check_output(["xcodebuild", "-version"], text=True).strip(),
        "runner_image": {key: os.environ.get(key) for key in ("ImageOS", "ImageVersion")},
        "source_sha256": {name: sha256(source / name) for name in sorted(provenance["files"])},
        "binary_sha256": sha256(output.parent / "unrar"),
        "upstream": {key: provenance[key] for key in ("version", "url", "sha256")},
    }
    output.write_text(json.dumps(data, indent=2) + "\n")


def validate_build(directory, root=ROOT):
    verify_source(root)
    for name in ("unrar", "license.txt", "acknow.txt", "build-info.json"):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Build artifact must contain a regular file: {name}")
    info = json.loads((directory / "build-info.json").read_text())
    if info["version"] != version(root) or info["architecture"] != "arm64":
        raise ValueError("Build version/architecture does not match this source")
    if sha256(directory / "unrar") != info["binary_sha256"]:
        raise ValueError("Binary changed since the native build")
    if info["minimum_macos"] != MIN_MACOS or info["sdk"] != "26.5":
        raise ValueError("Build minimum OS or SDK differs from the release toolchain")
    expected_files = set(json.loads((root / "upstream.json").read_text())["files"])
    if set(info["source_sha256"]) != expected_files:
        raise ValueError("Build source file list differs from this checkout")
    for name, checksum in info["source_sha256"].items():
        if sha256(root / SOURCE_DIR / name) != checksum:
            raise ValueError(f"Build is stale: {name} changed")
    for name in ("license.txt", "acknow.txt"):
        if sha256(directory / name) != sha256(root / SOURCE_DIR / name):
            raise ValueError(f"Build artifact differs from source: {name}")


def package_metadata(tag, directory, root=ROOT):
    release_version = check_tag(tag, root)
    dmg = directory / f"unrar_{release_version}_darwin_arm64.dmg"
    checksum = sha256(dmg)
    (directory / "checksums.txt").write_text(f"{checksum}  {dmg.name}\n")
    (directory / "unrar.rb").write_text(cask_text(release_version, checksum))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    sub.add_parser("check-tag").add_argument("tag")
    sub.add_parser("verify-source")
    preflight_parser = sub.add_parser("preflight")
    preflight_parser.add_argument("stage", choices=REQUIRED_SECRETS)
    preflight_parser.add_argument("tag")
    sub.add_parser("build-info").add_argument("output", type=Path)
    sub.add_parser("validate-build").add_argument("directory", type=Path)
    metadata = sub.add_parser("package-metadata")
    metadata.add_argument("tag")
    metadata.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "version":
        print(version())
    elif args.command == "check-tag":
        print(check_tag(args.tag))
    elif args.command == "verify-source":
        verify_source()
    elif args.command == "preflight":
        print(preflight(args.stage, args.tag))
    elif args.command == "build-info":
        build_info(args.output)
    elif args.command == "validate-build":
        validate_build(args.directory)
    else:
        package_metadata(args.tag, args.directory)


if __name__ == "__main__":
    main()
