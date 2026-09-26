#!/usr/bin/env python3
"""Tag a tested main-branch commit and dispatch Release using trusted main code."""
import argparse
import os
from release import REPOSITORY
from release_policy import api, require_tested_commit, source_tag, tag_commit


def tag_and_dispatch(commit, tag):
    # A draft may already contain signed bytes. Recover its existing run instead.
    if api(f"releases/tags/{tag}", missing_ok=True) is not None:
        raise ValueError("Release already exists; rerun failed jobs in its original Release run")
    target = tag_commit(tag, missing_ok=True)
    if target is not None:
        if target != commit:
            raise ValueError("Existing tag points to different source; never move a release tag")
    else:
        token = os.environ.get("RELEASE_TAG_TOKEN")
        if not token:
            raise ValueError("RELEASE_TAG_TOKEN is required to create protected release tags")
        api("git/refs", {"ref": f"refs/tags/{tag}", "sha": commit}, token=token)
    # Always load admission and orchestration from protected main, never the tag.
    api("actions/workflows/release.yml/dispatches",
        {"ref": "main", "inputs": {"tag": tag, "commit": commit}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    args = parser.parse_args()
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
                "GITHUB_WORKFLOW": "Prepare release", "GITHUB_REF": "refs/heads/main",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/prepare-release.yml@refs/heads/main"}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise ValueError("Run Prepare release from main in this repository's GitHub Actions")
    require_tested_commit(args.commit, os.environ["GITHUB_SHA"])
    tag = source_tag(args.commit)
    tag_and_dispatch(args.commit, tag)
    print(f"Dispatched Release for {tag} at {args.commit}. Follow it in the Actions tab.")


if __name__ == "__main__":
    main()
