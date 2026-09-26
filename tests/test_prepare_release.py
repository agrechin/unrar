import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("release", SCRIPTS / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
spec = importlib.util.spec_from_file_location("prepare_release", SCRIPTS / "prepare-release.py")
prepare = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"release": release}):
    spec.loader.exec_module(prepare)


class PrepareReleaseTests(unittest.TestCase):
    commit = "a" * 40
    tag = "v7.23.0"

    def ci(self, **overrides):
        return {"workflow_runs": [{"head_sha": self.commit, "status": "completed",
                                    "conclusion": "success", "id": 123, **overrides}]}

    def test_requires_full_sha_and_main_ancestry_before_querying_ci(self):
        with patch.object(prepare.subprocess, "run") as git, patch.object(prepare, "api") as api:
            for value in ("main", "a" * 7, "--help", self.commit + "\n"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    prepare.require_tested_commit(value)
            git.assert_not_called()
            api.assert_not_called()
            git.side_effect = subprocess.CalledProcessError(1, "git")
            with self.assertRaises(subprocess.CalledProcessError):
                prepare.require_tested_commit(self.commit)
            api.assert_not_called()

    def test_rejects_missing_failed_incomplete_or_different_commit_ci(self):
        cases = [{"workflow_runs": []}, self.ci(conclusion="failure"),
                 self.ci(status="in_progress"), self.ci(head_sha="b" * 40)]
        for response in cases:
            with self.subTest(response=response), patch.object(prepare.subprocess, "run"), \
                    patch.object(prepare, "api", return_value=response), self.assertRaises(ValueError):
                prepare.require_tested_commit(self.commit)

    def test_requires_both_linux_and_macos_validation(self):
        for jobs in ([{"name": "check", "conclusion": "success"}],
                     [{"name": "check", "conclusion": "success"},
                      {"name": "macos", "conclusion": "skipped"}]):
            with patch.object(prepare.subprocess, "run"), \
                    patch.object(prepare, "api", side_effect=[self.ci(), {"jobs": jobs}]), \
                    self.assertRaisesRegex(ValueError, "Both check and macos"):
                prepare.require_tested_commit(self.commit)
        jobs = [{"name": name, "conclusion": "success"} for name in ("check", "macos")]
        with patch.object(prepare.subprocess, "run"), \
                patch.object(prepare, "api", side_effect=[self.ci(), {"jobs": jobs}]):
            prepare.require_tested_commit(self.commit)

    def test_creates_tag_then_explicitly_dispatches_release(self):
        with patch.object(prepare, "api", return_value=None) as api:
            prepare.tag_and_dispatch(self.commit, self.tag)
            writes = [call.args for call in api.call_args_list if len(call.args) == 2]
            self.assertEqual(writes, [
                ("git/refs", {"ref": f"refs/tags/{self.tag}", "sha": self.commit}),
                ("actions/workflows/release.yml/dispatches",
                 {"ref": self.tag, "inputs": {"tag": self.tag}}),
            ])

    def test_existing_release_or_different_tag_cannot_be_replaced(self):
        cases = [[{"draft": False}], [{"draft": True}],
                 [None, {"object": {"type": "commit", "sha": "b" * 40}}]]
        for responses in cases:
            with self.subTest(responses=responses), \
                    patch.object(prepare, "api", side_effect=responses) as api, \
                    self.assertRaises(ValueError):
                prepare.tag_and_dispatch(self.commit, self.tag)
            self.assertTrue(all(len(call.args) == 1 for call in api.call_args_list))

    def test_same_source_tag_can_retry_dispatch_without_recreating_tag(self):
        for annotated in (False, True):
            target = {"type": "commit", "sha": self.commit}
            responses = [None, {"object": {"type": "tag", "sha": "c" * 40} if annotated else target}]
            if annotated:
                responses.append({"object": target})
            responses.append(None)
            with self.subTest(annotated=annotated), patch.object(prepare, "api", side_effect=responses) as api:
                prepare.tag_and_dispatch(self.commit, self.tag)
                writes = [call.args[0] for call in api.call_args_list if len(call.args) == 2]
                self.assertEqual(writes, ["actions/workflows/release.yml/dispatches"])

    def test_api_errors_fail_closed_except_explicit_optional_404(self):
        for error in ("gh: Not Found (HTTP 404)", "gh: Forbidden (HTTP 403)", "network error"):
            result = subprocess.CompletedProcess([], 1, "", error)
            with patch.object(prepare.subprocess, "run", return_value=result):
                with self.assertRaises(RuntimeError):
                    prepare.api("example")
                if "404" in error:
                    self.assertIsNone(prepare.api("example", missing_ok=True))
                else:
                    with self.assertRaises(RuntimeError):
                        prepare.api("example", missing_ok=True)
