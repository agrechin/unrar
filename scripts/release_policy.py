"""Release admission, executed only from the trusted main workflow checkout."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from release import REPOSITORY, check_tag, verify_source, version


def api(path, payload=None, missing_ok=False, token=None):
    command = ["gh", "api", f"repos/{REPOSITORY}/{path}"]
    if payload is not None:
        command += ["--method", "POST", "--input", "-"]
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True,
                            env={**os.environ, "GH_TOKEN": token} if token is not None else None)
    if result.returncode:
        if missing_ok and "(HTTP 404)" in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


def require_sha(commit):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Supply the full 40-character commit SHA from passing CI on main")


def require_tested_commit(commit, main_commit):
    require_sha(commit)
    require_sha(main_commit)
    # Use the workflow's main snapshot, not a branch that can change mid-run.
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, main_commit], check=True)
    runs = api(f"actions/workflows/ci.yml/runs?branch=main&event=push&head_sha={commit}&per_page=1")
    if not runs["workflow_runs"]:
        raise ValueError("No CI push run on main for this commit")
    run = runs["workflow_runs"][0]
    if (run["head_sha"] != commit or run["head_branch"] != "main" or run["event"] != "push"
            or run["status"] != "completed" or run["conclusion"] != "success"):
        raise ValueError("The latest CI push run on main must have completed successfully")
    jobs = api(f"actions/runs/{run['id']}/jobs?filter=latest&per_page=100")["jobs"]
    passed = {job["name"] for job in jobs if job["conclusion"] == "success"}
    if not {"check", "macos"} <= passed:
        raise ValueError("Both check and macos jobs must pass; older Linux-only CI is insufficient")


def tag_commit(tag, missing_ok=False):
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Release tag must be a stable vMAJOR.MINOR.PATCH version")
    ref = api(f"git/ref/tags/{tag}", missing_ok=missing_ok)
    if ref is None:
        return None
    target = ref["object"]
    seen = set()
    while target["type"] == "tag":
        require_sha(target["sha"])
        if target["sha"] in seen or len(seen) >= 16:
            raise ValueError("Invalid annotated release tag chain")
        seen.add(target["sha"])
        target = api(f"git/tags/{target['sha']}")["object"]
    if target["type"] != "commit":
        raise ValueError("Release tag must point to a commit")
    require_sha(target["sha"])
    return target["sha"]


def require_tag_commit(tag, commit):
    require_sha(commit)
    if tag_commit(tag) != commit:
        raise ValueError("Release tag points to different source; never move a release tag")


def source_tag(commit):
    # Inspect candidate data with trusted tooling; never execute its scripts.
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "source"
        subprocess.run(["git", "worktree", "add", "--detach", str(source), commit], check=True)
        try:
            verify_source(source)
            tag = "v" + version(source)
            check_tag(tag, source)
            return tag
        finally:
            subprocess.run(["git", "worktree", "remove", str(source)], check=True)


def authorize_release(tag, commit, main_commit):
    require_tag_commit(tag, commit)
    require_tested_commit(commit, main_commit)
    if source_tag(commit) != tag:
        raise ValueError("Release tag does not match the authorized source version")
    return commit
