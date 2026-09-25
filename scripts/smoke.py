#!/usr/bin/env python3
"""Exercise the actual binary with upstream RAR4 and RAR5 archives."""
import binascii
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    binary = Path(sys.argv[1]).resolve()
    fixtures = ROOT / "tests/fixtures"
    manifest = json.loads((fixtures / "manifest.json").read_text())
    for name, expected in manifest.items():
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            lines = (fixtures / name).read_bytes().splitlines()
            start = next(i for i, line in enumerate(lines) if line.startswith(b"begin "))
            data = b"".join(binascii.a2b_uu(line) for line in lines[start + 1:]
                            if line not in (b"end", b"", b"`"))
            archive = work / "fixture.rar"
            archive.write_bytes(data)
            if hashlib.sha256(data).hexdigest() != expected["archive_sha256"]:
                raise ValueError(f"Fixture checksum mismatch: {name}")
            subprocess.run([str(binary), "t", "-idq", str(archive)], check=True)
            destination = work / "extracted"
            destination.mkdir()
            subprocess.run([str(binary), "x", "-idq", "-o-", str(archive),
                            str(destination) + "/"], check=True)
            for path, checksum in expected["files"].items():
                actual = hashlib.sha256((destination / path).read_bytes()).hexdigest()
                if actual != checksum:
                    raise ValueError(f"Extraction mismatch: {name}: {path}")
            damaged = work / "invalid.rar"
            damaged.write_bytes(b"This is not a RAR archive.\n")
            result = subprocess.run([str(binary), "t", "-idq", str(damaged)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                raise ValueError("Invalid archive was unexpectedly accepted")
            print(f"PASS {name}: integrity, extraction content, invalid archive rejection")


if __name__ == "__main__":
    main()
