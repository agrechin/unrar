#!/usr/bin/env python3
"""Replace vendor/unrar and upstream.json from a verified stable RARLAB archive."""
import argparse
import json
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

from release import ROOT, SOURCE_DIR, sha256, verify_source, version


def import_upstream(archive, url, checksum, root=ROOT):
    if not re.fullmatch(r"https://www\.rarlab\.com/rar/unrarsrc-[0-9.]+\.tar\.gz", url):
        raise ValueError("Use a versioned HTTPS source archive URL from www.rarlab.com/rar")
    if not re.fullmatch(r"[a-f0-9]{64}", checksum) or sha256(archive) != checksum:
        raise ValueError("Archive SHA-256 does not match the expected checksum")
    # Refuse to discard local source edits or an incomplete previous import.
    verify_source(root)
    with tempfile.TemporaryDirectory(prefix=".unrar-import-", dir=root) as temporary:
        stage = Path(temporary)
        source = stage / SOURCE_DIR
        source.mkdir(parents=True)
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle:
                if member.isdir() and member.name.rstrip("/") == "unrar":
                    continue
                parts = member.name.split("/")
                if (not member.isfile() or len(parts) != 2 or parts[0] != "unrar"
                        or parts[1] in ("", ".", "..") or "\\" in parts[1]):
                    raise ValueError(f"Unexpected archive entry: {member.name}")
                target = source / parts[1]
                # Explicit copies reject links, traversal, and duplicate entries.
                with bundle.extractfile(member) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
        for name in ("version.hpp", "makefile", "license.txt", "acknow.txt"):
            if not (source / name).is_file():
                raise ValueError(f"Missing required upstream file: {name}")
        current = version(stage)
        if "-beta." in current:
            raise ValueError("Import requires stable upstream source (RARVER_BETA must be 0)")
        provenance = {
            "version": current, "url": url, "sha256": checksum,
            "files": {p.name: sha256(p) for p in sorted(source.iterdir())},
        }
        manifest = stage / "upstream.json"
        manifest.write_text(json.dumps(provenance, indent=2) + "\n")
        verify_source(stage)
        destination = root / SOURCE_DIR
        previous = stage / "previous"
        destination.rename(previous)
        try:
            source.rename(destination)
            manifest.replace(root / "upstream.json")
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            previous.rename(destination)
            raise
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Downloaded unrarsrc-*.tar.gz")
    parser.add_argument("--url", required=True, help="Exact official versioned download URL")
    parser.add_argument("--sha256", required=True, help="Expected archive SHA-256")
    args = parser.parse_args()
    try:
        current = import_upstream(args.archive, args.url, args.sha256)
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"Import failed: {error}\n")
    print(f"Imported UnRAR {current} into {SOURCE_DIR}; updated upstream.json.")
    print("Review the diff, update README.md, and run the checks in docs/upgrading.md.")


if __name__ == "__main__":
    main()
