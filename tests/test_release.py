import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("release", Path(__file__).resolve().parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def source_fixture(self, root, beta=0):
        source = root / release.SOURCE_DIR
        source.mkdir(parents=True)
        (source / "version.hpp").write_text(
            f"#define RARVER_MAJOR 7\n#define RARVER_MINOR 23\n#define RARVER_BETA {beta}\n")
        (source / "example.cpp").write_text("// upstream source\n")
        (root / "upstream.json").write_text(json.dumps({
            "version": release.version(root),
            "files": {name: release.sha256(source / name) for name in ("version.hpp", "example.cpp")},
        }))

    def release_environment(self, stage, tag):
        return {
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "agrechin/unrar",
            "GITHUB_WORKFLOW": "Release", "GITHUB_REF": f"refs/tags/{tag}",
            **{name: "test-placeholder" for name in release.REQUIRED_SECRETS[stage]},
        }

    def test_beta_and_stable_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / release.SOURCE_DIR
            source.mkdir(parents=True)
            for beta, expected in [(1, "7.30.0-beta.1"), (0, "7.30.0")]:
                (source / "version.hpp").write_text(
                    f"#define RARVER_MAJOR 7\n#define RARVER_MINOR 30\n#define RARVER_BETA {beta}\n")
                self.assertEqual(release.version(root), expected)

    def test_tag_cannot_mislabel_source(self):
        with self.assertRaises(ValueError):
            release.check_tag("v0.0.0")

    def test_beta_source_cannot_release_even_with_matching_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source_fixture(root, beta=1)
            with self.assertRaisesRegex(ValueError, "stable upstream source"):
                release.check_tag("v7.23.0-beta.1", root)

    def test_beta_cannot_generate_cask(self):
        with self.assertRaisesRegex(ValueError, "stable release version"):
            release.cask_text("7.23.0-beta.1", "a" * 64)

    def test_release_context_and_credentials_fail_closed(self):
        tag = "v7.23.0"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source_fixture(root)
            for stage in ("sign", "publish"):
                env = self.release_environment(stage, tag)
                self.assertEqual(release.preflight(stage, tag, root, env), "7.23.0")
                for name in release.REQUIRED_SECRETS[stage]:
                    with self.subTest(stage=stage, missing=name):
                        with self.assertRaisesRegex(ValueError, name):
                            release.preflight(stage, tag, root, {**env, name: ""})
                for overrides in ({"GITHUB_ACTIONS": "false"},
                                  {"GITHUB_REPOSITORY": "someone/unrar"},
                                  {"GITHUB_WORKFLOW": "CI"},
                                  {"GITHUB_REF": "refs/heads/main"},
                                  {"GITHUB_REF": "refs/tags/v0.0.0"}):
                    with self.subTest(stage=stage, context=overrides):
                        with self.assertRaisesRegex(ValueError, "GitHub Release workflow"):
                            release.preflight(stage, tag, root, {**env, **overrides})

    def test_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source_fixture(root)
            release.verify_source(root)
            source = root / release.SOURCE_DIR
            original = (source / "example.cpp").read_bytes()
            (source / "example.cpp").write_text("// modified source\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release.verify_source(root)
            (source / "example.cpp").write_bytes(original)
            (source / "extra.cpp").touch()
            with self.assertRaisesRegex(ValueError, "Unrecorded upstream"):
                release.verify_source(root)

    def test_release_entrypoints_reject_local_execution(self):
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        commands = (["bash", str(scripts / "sign-notarize.sh")],
                    ["bash", str(scripts / "publish.sh")],
                    [sys.executable, str(scripts / "publish-tap.py")])
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run([*command, "v7.23.0", "unused.rb"],
                                        env={"PATH": os.environ["PATH"]},
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("GitHub Release workflow", result.stderr)

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
