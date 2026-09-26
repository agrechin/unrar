#!/usr/bin/env python3
"""Tag a tested main-branch commit and dispatch the tag-scoped Release workflow."""
import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from release import REPOSITORY, check_tag, verify_source, version


def api(path, payload=None, missing_ok=False):
    command = ["gh", "api", f"repos/{REPOSITORY}/{path}"]
    if payload is not None:
        command += ["--method", "POST", "--input", "-"]
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True)
    if result.returncode:
        if missing_ok and "(HTTP 404)" in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


def require_tested_commit(commit):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Supply the full 40-character commit SHA from passing CI on main")
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], check=True)
    runs = api(f"actions/workflows/ci.yml/runs?branch=main&event=push&head_sha={commit}&per_page=1")
    if not runs["workflow_runs"]:
        raise ValueError("No CI push run on main for this commit")
    run = runs["workflow_runs"][0]
    if (run["head_sha"] != commit or run["status"] != "completed"
            or run["conclusion"] != "success"):
        raise ValueError("The latest CI push run on main must have completed successfully")
    jobs = api(f"actions/runs/{run['id']}/jobs?filter=latest&per_page=100")["jobs"]
    passed = {job["name"] for job in jobs if job["conclusion"] == "success"}
    if not {"check", "macos"} <= passed:
        raise ValueError("Both check and macos jobs must pass; older Linux-only CI is insufficient")


def tag_and_dispatch(commit, tag):
    # A draft may already contain signed bytes. Recover its existing run instead.
    if api(f"releases/tags/{tag}", missing_ok=True) is not None:
        raise ValueError("Release already exists; rerun failed jobs in its original Release run")
    ref = api(f"git/ref/tags/{tag}", missing_ok=True)
    if ref is not None:
        target = ref["object"]
        while target["type"] == "tag":
            target = api(f"git/tags/{target['sha']}")["object"]
        if target["type"] != "commit" or target["sha"] != commit:
            raise ValueError("Existing tag points to different source; never move a release tag")
    else:
        api("git/refs", {"ref": f"refs/tags/{tag}", "sha": commit})
    # GITHUB_TOKEN-created tags do not trigger push workflows. Explicit dispatch
    # is supported with that token and runs Release in the tag's own context.
    api("actions/workflows/release.yml/dispatches", {"ref": tag, "inputs": {"tag": tag}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    args = parser.parse_args()
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
                "GITHUB_WORKFLOW": "Prepare release", "GITHUB_REF": "refs/heads/main"}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise ValueError("Run Prepare release from main in this repository's GitHub Actions")
    require_tested_commit(args.commit)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "source"
        subprocess.run(["git", "worktree", "add", "--detach", str(source), args.commit], check=True)
        try:
            verify_source(source)
            tag = "v" + version(source)
            check_tag(tag, source)
        finally:
            subprocess.run(["git", "worktree", "remove", str(source)], check=True)
    tag_and_dispatch(args.commit, tag)
    print(f"Dispatched Release for {tag} at {args.commit}. Follow it in the Actions tab.")


if __name__ == "__main__":
    main()
