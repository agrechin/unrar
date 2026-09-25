#!/usr/bin/env python3
"""Version and release metadata; standard library only."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "agrechin/unrar"
MIN_MACOS = "12.0"


def version(root=ROOT):
    values = dict(re.findall(r"^#define RARVER_(MAJOR|MINOR|BETA)\s+(\d+)$",
                             (root / "version.hpp").read_text(), re.MULTILINE))
    major, minor, beta = (int(values[k]) for k in ("MAJOR", "MINOR", "BETA"))
    return f"{major}.{minor}.0" + (f"-beta.{beta}" if beta else "")


def check_tag(tag):
    expected = f"v{version()}"
    if tag != expected:
        raise ValueError(f"Tag must match version.hpp: expected {expected}, got {tag!r}")
    return tag[1:]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cask_text(release_version, checksum):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-beta\.\d+)?", release_version):
        raise ValueError("Invalid release version")
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


def build_info(output):
    files = sorted([*ROOT.glob("*.cpp"), *ROOT.glob("*.hpp"),
                    ROOT / "makefile", ROOT / "license.txt", ROOT / "acknow.txt"])
    sdk = json.loads(Path("/sdk/SDKSettings.json").read_text())
    data = {
        "version": version(), "architecture": "arm64", "minimum_macos": MIN_MACOS,
        "sdk": sdk["Version"] if "Version" in sdk else sdk["CanonicalName"],
        "compiler": subprocess.check_output(["clang++", "--version"], text=True).strip(),
        "source_sha256": {p.name: sha256(p) for p in files},
        "binary_sha256": sha256(output.parent / "unrar"),
    }
    output.write_text(json.dumps(data, indent=2) + "\n")


def validate_build(directory):
    info = json.loads((directory / "build-info.json").read_text())
    if info["version"] != version() or info["architecture"] != "arm64":
        raise ValueError("Build version/architecture does not match this source")
    if sha256(directory / "unrar") != info["binary_sha256"]:
        raise ValueError("Binary changed since the Docker build")
    expected_files = {p.name for p in [*ROOT.glob("*.cpp"), *ROOT.glob("*.hpp"),
                                     ROOT / "makefile", ROOT / "license.txt", ROOT / "acknow.txt"]}
    if set(info["source_sha256"]) != expected_files:
        raise ValueError("Build source file list differs from this checkout")
    for name, checksum in info["source_sha256"].items():
        if sha256(ROOT / name) != checksum:
            raise ValueError(f"Build is stale: {name} changed")


def package_metadata(tag, directory):
    release_version = check_tag(tag)
    dmg = directory / f"unrar_{release_version}_darwin_arm64.dmg"
    checksum = sha256(dmg)
    (directory / "checksums.txt").write_text(f"{checksum}  {dmg.name}\n")
    (directory / "unrar.rb").write_text(cask_text(release_version, checksum))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    sub.add_parser("check-tag").add_argument("tag")
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
    elif args.command == "build-info":
        build_info(args.output)
    elif args.command == "validate-build":
        validate_build(args.directory)
    else:
        package_metadata(args.tag, args.directory)


if __name__ == "__main__":
    main()
