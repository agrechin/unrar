import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release_policy as policy


class ReleaseAuthorizationTests(unittest.TestCase):
    tag = "v7.23.0"

    def git(self, *args):
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.enterContext(contextlib.chdir(self.root))
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Release test")
        self.git("config", "user.email", "release@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        source = self.root / "vendor/unrar"
        source.mkdir(parents=True)
        (source / "version.hpp").write_text(
            "#define RARVER_MAJOR 7\n#define RARVER_MINOR 23\n#define RARVER_BETA 0\n")
        (self.root / "upstream.json").write_text(json.dumps({
            "version": "7.23.0", "files": {"version.hpp": hashlib.sha256(
                (source / "version.hpp").read_bytes()).hexdigest()},
        }))
        # Admission must read candidate data without executing candidate tooling.
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "release.py").write_text("raise RuntimeError('candidate code executed')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("tag", self.tag)
        self.api = self.enterContext(patch.object(policy, "api", side_effect=self.response))

    def response(self, path, **_kwargs):
        if path == f"git/ref/tags/{self.tag}":
            obj = self.git("rev-parse", self.tag)
            return {"object": {"sha": obj, "type": self.git("cat-file", "-t", obj)}}
        if path.startswith("git/tags/"):
            obj = self.git("rev-parse", path.rsplit("/", 1)[1] + "^{}")
            return {"object": {"sha": obj, "type": "commit"}}
        if path.startswith("actions/workflows/ci.yml/runs?"):
            return {"workflow_runs": [{"head_sha": self.commit, "head_branch": "main",
                                       "event": "push", "status": "completed",
                                       "conclusion": "success", "id": 123}]}
        if path.startswith("actions/runs/123/jobs?"):
            return {"jobs": [{"name": name, "conclusion": "success"} for name in ("check", "macos")]}
        raise AssertionError(f"Unexpected request: {path}")

    def test_tested_main_commit_and_annotated_tag_are_authorized_without_candidate_execution(self):
        for annotated in (False, True):
            if annotated:
                self.git("-c", "tag.gpgsign=false", "tag", "-fa", self.tag, "-m", "release")
            self.assertEqual(policy.authorize_release(self.tag, self.commit, self.commit), self.commit)

    def test_main_controller_preflights_candidate_as_data(self):
        env = {**os.environ, "UNRAR_SOURCE_ROOT": str(self.root),
               "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "agrechin/unrar",
               "GITHUB_WORKFLOW": "Release", "GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "RELEASE_TAG": self.tag,
               "GITHUB_WORKFLOW_REF": "agrechin/unrar/.github/workflows/release.yml@refs/heads/main",
               "RELEASE_COMMIT": self.commit,
               **{name: "fixture" for name in ("MACOS_SIGN_P12", "MACOS_SIGN_PASSWORD",
                                               "MACOS_NOTARY_KEY", "MACOS_NOTARY_KEY_ID",
                                               "MACOS_NOTARY_ISSUER_ID")}}
        result = subprocess.check_output(
            [sys.executable, str(ROOT / "scripts/release.py"), "preflight", "sign", self.tag],
            env=env, text=True)
        self.assertEqual(result.strip(), "7.23.0")

    def test_off_main_commit_is_rejected_even_with_matching_tag_and_successful_ci(self):
        main = self.commit
        self.git("checkout", "-qb", "attacker")
        self.git("commit", "--allow-empty", "-qm", "unreviewed tooling")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("tag", "-f", self.tag)
        with self.assertRaises(subprocess.CalledProcessError):
            policy.authorize_release(self.tag, self.commit, main)
        self.assertFalse(any(call.args[0].startswith("actions/") for call in self.api.call_args_list))

    def test_old_tested_main_commit_remains_eligible(self):
        self.git("commit", "--allow-empty", "-qm", "new main")
        main = self.git("rev-parse", "HEAD")
        self.assertEqual(policy.authorize_release(self.tag, self.commit, main), self.commit)

    def test_moving_tag_cannot_change_authorized_checkout_or_publish_label(self):
        authorized = policy.authorize_release(self.tag, self.commit, self.commit)
        self.git("commit", "--allow-empty", "-qm", "replacement tooling")
        self.git("tag", "-f", self.tag)
        with self.assertRaisesRegex(ValueError, "different source"):
            policy.require_tag_commit(self.tag, authorized)
        self.git("checkout", "--detach", authorized)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.commit)
        self.assertNotEqual(self.git("rev-parse", self.tag), self.commit)

    def test_invalid_tag_forms_fail_before_api_or_git(self):
        for tag in ("main", "v7.23.0\n", "v7.23.0/../../heads/main", "v7.23.0-beta.1", "--help"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                policy.authorize_release(tag, self.commit, self.commit)
        self.api.assert_not_called()

    def test_non_commit_and_cyclic_annotated_tags_fail_closed(self):
        for obj in ({"type": "tree", "sha": "a" * 40}, {"type": "tag", "sha": "a" * 40}):
            with patch.object(policy, "api", return_value={"object": obj}), self.assertRaises(ValueError):
                policy.tag_commit(self.tag)

    def test_authorization_does_not_output_commit_after_failed_ci_or_wrong_version(self):
        with patch.object(policy, "require_tested_commit", side_effect=ValueError("failed CI")), \
                patch.object(policy, "source_tag") as source, self.assertRaises(ValueError):
            policy.authorize_release(self.tag, self.commit, self.commit)
        source.assert_not_called()
        with patch.object(policy, "source_tag", return_value="v1.0.0"), \
                self.assertRaisesRegex(ValueError, "source version"):
            policy.authorize_release(self.tag, self.commit, self.commit)


class ReleaseWorkflowTests(unittest.TestCase):
    def test_candidate_build_and_binary_execution_are_separate_from_secret_jobs(self):
        # Validate the actual workflow graph, including publication-only reruns.
        workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(set(workflow["on"]["workflow_dispatch"]["inputs"]), {"tag", "commit"})
        jobs = workflow["jobs"]
        admission = jobs["authorize"]
        self.assertEqual(admission["if"], "github.ref == 'refs/heads/main'")
        self.assertEqual(set(jobs), {"authorize", "check", "build", "package", "verify", "publish"})
        for name, job in jobs.items():
            checkouts = [step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")]
            self.assertTrue(checkouts)
            for step in checkouts:
                self.assertEqual(step["with"]["persist-credentials"], "false")
            if name != "authorize":
                needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
                self.assertIn("authorize", needs)
            if name in ("build", "package", "publish"):
                self.assertEqual(job["env"]["UNRAR_SOURCE_ROOT"], "${{ github.workspace }}/source")
                self.assertEqual([(step["with"]["ref"], step["with"].get("path")) for step in checkouts], [
                    ("${{ github.sha }}", "control"),
                    ("${{ needs.authorize.outputs.commit }}", "source"),
                ])
                for step in job["steps"]:
                    if "run" in step:
                        self.assertIn("control/scripts/", step["run"])
                        self.assertNotIn("source/scripts/", step["run"])
                if name == "build":
                    self.assertNotIn("environment", job)
                    self.assertNotIn("secrets.", json.dumps(job))
                else:
                    self.assertEqual(job["environment"], "release")
                    self.assertEqual(job["env"]["RELEASE_COMMIT"], "${{ needs.authorize.outputs.commit }}")
            else:
                self.assertNotIn("environment", job)
                self.assertNotIn("secrets.", json.dumps(job))
                expected = "${{ github.sha }}" if name in ("authorize", "verify") else "${{ needs.authorize.outputs.commit }}"
                self.assertEqual([step["with"]["ref"] for step in checkouts], [expected])
        self.assertIn("check", jobs["build"]["needs"])
        self.assertIn("build", jobs["package"]["needs"])
        self.assertIn("package", jobs["verify"]["needs"])
        self.assertIn("verify", jobs["publish"]["needs"])
        self.assertIn("bash control/scripts/build.sh", json.dumps(jobs["build"]))
        self.assertNotIn("build.sh", json.dumps(jobs["package"]))
        self.assertIn("bash scripts/verify-release.sh", json.dumps(jobs["verify"]))
        self.assertIn("bash control/scripts/sign-notarize.sh", json.dumps(jobs["package"]))
        self.assertIn("bash control/scripts/publish.sh", json.dumps(jobs["publish"]))


if __name__ == "__main__":
    unittest.main()
