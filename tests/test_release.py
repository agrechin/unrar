import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("release", Path(__file__).resolve().parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_beta_and_stable_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for beta, expected in [(1, "7.30.0-beta.1"), (0, "7.30.0")]:
                (root / "version.hpp").write_text(
                    f"#define RARVER_MAJOR 7\n#define RARVER_MINOR 30\n#define RARVER_BETA {beta}\n")
                self.assertEqual(release.version(root), expected)

    def test_tag_cannot_mislabel_source(self):
        with self.assertRaises(ValueError):
            release.check_tag("v0.0.0")

    def test_cask_rejects_interpolation(self):
        for version in ['1.2.3#{system("false")}', '../../bad', '1.2.3\n']:
            with self.assertRaises(ValueError):
                release.cask_text(version, "a" * 64)
        with self.assertRaises(ValueError):
            release.cask_text("1.2.3", "no_check")

    def test_metadata_hashes_the_final_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            version = release.version()
            artifact = directory / f"unrar_{version}_darwin_arm64.dmg"
            artifact.write_bytes(b"final stapled bytes")
            release.package_metadata(f"v{version}", directory)
            checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual((directory / "checksums.txt").read_text(), f"{checksum}  {artifact.name}\n")
            cask = (directory / "unrar.rb").read_text()
            self.assertIn(checksum, cask)
            self.assertIn('depends_on arch: :arm64', cask)
            self.assertNotIn('xattr', cask)

    def test_stale_binary_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "unrar").write_bytes(b"changed")
            (directory / "build-info.json").write_text(json.dumps({
                "version": release.version(), "architecture": "arm64",
                "binary_sha256": "0" * 64,
            }))
            with self.assertRaisesRegex(ValueError, "Binary changed"):
                release.validate_build(directory)
