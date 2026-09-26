import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("release", SCRIPTS / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
sys.path.insert(0, str(SCRIPTS))
import release_policy as policy

spec = importlib.util.spec_from_file_location("prepare_release", SCRIPTS / "prepare-release.py")
prepare = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"release": release}):
    spec.loader.exec_module(prepare)


class PrepareReleaseTests(unittest.TestCase):
    commit = "a" * 40
    tag = "v7.23.0"

    def ci(self, **overrides):
        return {"workflow_runs": [{"head_sha": self.commit, "status": "completed",
                                    "conclusion": "success", "id": 123, "head_branch": "main",
                                    "event": "push", **overrides}]}

    def test_requires_full_sha_and_main_ancestry_before_querying_ci(self):
        with patch.object(policy.subprocess, "run") as git, patch.object(policy, "api") as api:
            for value in ("main", "a" * 7, "--help", self.commit + "\n"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    policy.require_tested_commit(value, self.commit)
            git.assert_not_called()
            api.assert_not_called()
            git.side_effect = subprocess.CalledProcessError(1, "git")
            with self.assertRaises(subprocess.CalledProcessError):
                policy.require_tested_commit(self.commit, self.commit)
            api.assert_not_called()

    def test_rejects_missing_failed_incomplete_or_different_commit_ci(self):
        cases = [{"workflow_runs": []}, self.ci(conclusion="failure"),
                 self.ci(status="in_progress"), self.ci(head_sha="b" * 40),
                 self.ci(head_branch="feature"), self.ci(event="pull_request")]
        for response in cases:
            with self.subTest(response=response), patch.object(policy.subprocess, "run"), \
                    patch.object(policy, "api", return_value=response), self.assertRaises(ValueError):
                policy.require_tested_commit(self.commit, self.commit)

    def test_requires_both_linux_and_macos_validation(self):
        for jobs in ([{"name": "check", "conclusion": "success"}],
                     [{"name": "check", "conclusion": "success"},
                      {"name": "macos", "conclusion": "skipped"}]):
            with patch.object(policy.subprocess, "run"), \
                    patch.object(policy, "api", side_effect=[self.ci(), {"jobs": jobs}]), \
                    self.assertRaisesRegex(ValueError, "Both check and macos"):
                policy.require_tested_commit(self.commit, self.commit)
        jobs = [{"name": name, "conclusion": "success"} for name in ("check", "macos")]
        with patch.object(policy.subprocess, "run"), \
                patch.object(policy, "api", side_effect=[self.ci(), {"jobs": jobs}]):
            policy.require_tested_commit(self.commit, self.commit)

    @patch.dict(os.environ, {"RELEASE_TAG_TOKEN": "test-tag-token"})
    def test_creates_tag_then_explicitly_dispatches_release(self):
        with patch.object(prepare, "api", return_value=None) as api, \
                patch.object(prepare, "tag_commit", return_value=None):
            prepare.tag_and_dispatch(self.commit, self.tag)
            writes = [call.args for call in api.call_args_list if len(call.args) == 2]
            self.assertEqual(writes, [
                ("git/refs", {"ref": f"refs/tags/{self.tag}", "sha": self.commit}),
                ("actions/workflows/release.yml/dispatches",
                 {"ref": "main", "inputs": {"tag": self.tag, "commit": self.commit}}),
            ])
            self.assertEqual(api.call_args_list[1].kwargs["token"], "test-tag-token")

    def test_tag_creation_requires_dedicated_credential(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(prepare, "api", return_value=None) as api, \
                patch.object(prepare, "tag_commit", return_value=None), \
                self.assertRaisesRegex(ValueError, "RELEASE_TAG_TOKEN"):
            prepare.tag_and_dispatch(self.commit, self.tag)
        self.assertTrue(all(len(call.args) == 1 for call in api.call_args_list))

    def test_existing_release_or_different_tag_cannot_be_replaced(self):
        for existing in ({"draft": False}, {"draft": True}):
            with patch.object(prepare, "api", return_value=existing) as api, \
                    self.assertRaisesRegex(ValueError, "Release already exists"):
                prepare.tag_and_dispatch(self.commit, self.tag)
            self.assertTrue(all(len(call.args) == 1 for call in api.call_args_list))
        with patch.object(prepare, "api", return_value=None) as api, \
                patch.object(prepare, "tag_commit", return_value="b" * 40), \
                self.assertRaisesRegex(ValueError, "different source"):
            prepare.tag_and_dispatch(self.commit, self.tag)
        self.assertTrue(all(len(call.args) == 1 for call in api.call_args_list))

    def test_same_source_tag_can_retry_dispatch_without_recreating_tag(self):
        with patch.object(prepare, "api", return_value=None) as api, \
                patch.object(prepare, "tag_commit", return_value=self.commit):
            prepare.tag_and_dispatch(self.commit, self.tag)
            writes = [call.args[0] for call in api.call_args_list if len(call.args) == 2]
            self.assertEqual(writes, ["actions/workflows/release.yml/dispatches"])

    def test_api_errors_fail_closed_except_explicit_optional_404(self):
        for error in ("gh: Not Found (HTTP 404)", "gh: Forbidden (HTTP 403)", "network error"):
            result = subprocess.CompletedProcess([], 1, "", error)
            with patch.object(policy.subprocess, "run", return_value=result):
                with self.assertRaises(RuntimeError):
                    policy.api("example")
                if "404" in error:
                    self.assertIsNone(policy.api("example", missing_ok=True))
                else:
                    with self.assertRaises(RuntimeError):
                        policy.api("example", missing_ok=True)
