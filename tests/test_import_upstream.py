import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("release", SCRIPTS / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
spec = importlib.util.spec_from_file_location("import_upstream", SCRIPTS / "import-upstream.py")
upstream = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"release": release}):
    spec.loader.exec_module(upstream)


class ImportTests(unittest.TestCase):
    url = "https://www.rarlab.com/rar/unrarsrc-7.3.1.tar.gz"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / release.SOURCE_DIR
        self.source.mkdir(parents=True)
        (self.source / "version.hpp").write_text(
            "#define RARVER_MAJOR 7\n#define RARVER_MINOR 23\n#define RARVER_BETA 0\n")
        (self.source / "obsolete.cpp").write_bytes(b"old source\r\n")
        (self.root / "upstream.json").write_text(json.dumps({
            "version": "7.23.0",
            "files": {p.name: release.sha256(p) for p in self.source.iterdir()},
        }))
        (self.root / "README.md").write_text("Repository tooling stays intact.\n")

    def archive(self, beta=0, extra=None):
        self.files = {
            "version.hpp": (f"#define RARVER_MAJOR 7\n#define RARVER_MINOR 30\n"
                            f"#define RARVER_BETA {beta}\n").encode(),
            "makefile": b"# upstream makefile\r\n",
            "license.txt": b"upstream license\r\n",
            "acknow.txt": b"upstream acknowledgements\r\n",
            "new.cpp": b"// new source\r\n",
        }
        archive = self.root / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name, content in self.files.items():
                member = tarfile.TarInfo(f"unrar/{name}")
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
            if extra:
                bundle.addfile(extra)
        return archive

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in [*self.source.iterdir(), self.root / "upstream.json", self.root / "README.md"]}

    def test_replaces_complete_snapshot_and_preserves_exact_bytes(self):
        archive = self.archive()
        checksum = release.sha256(archive)
        self.assertEqual(upstream.import_upstream(archive, self.url, checksum, self.root), "7.30.0")
        self.assertEqual({p.name: p.read_bytes() for p in self.source.iterdir()}, self.files)
        manifest = json.loads((self.root / "upstream.json").read_text())
        self.assertEqual((manifest["version"], manifest["url"], manifest["sha256"]),
                         ("7.30.0", self.url, checksum))
        release.verify_source(self.root)
        self.assertEqual((self.root / "README.md").read_text(), "Repository tooling stays intact.\n")

    def test_invalid_imports_leave_checkout_unchanged(self):
        symlink = tarfile.TarInfo("unrar/link.cpp")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "../../README.md"
        cases = [
            {"checksum": "0" * 64},
            {"beta": 1},
            {"url": "https://example.com/source.tar.gz"},
            {"extra": tarfile.TarInfo("unrar/../../README.md")},
            {"extra": symlink},
            {"extra": tarfile.TarInfo("unrar/new.cpp")},
        ]
        for case in cases:
            with self.subTest(case=case):
                archive = self.archive(beta=case.get("beta", 0), extra=case.get("extra"))
                before = self.snapshot()
                with self.assertRaises((ValueError, FileExistsError)):
                    upstream.import_upstream(archive, case.get("url", self.url),
                                             case.get("checksum", release.sha256(archive)), self.root)
                self.assertEqual(self.snapshot(), before)

    def test_local_source_edits_are_not_discarded(self):
        archive = self.archive()
        (self.source / "obsolete.cpp").write_text("local edits\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            upstream.import_upstream(archive, self.url, release.sha256(archive), self.root)
        self.assertEqual(self.snapshot(), before)
