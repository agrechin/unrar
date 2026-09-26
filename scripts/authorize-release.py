#!/usr/bin/env python3
"""Authorize a release before candidate code or release credentials are used."""
import argparse
import os
from pathlib import Path

from release import REPOSITORY
from release_policy import authorize_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("commit")
    args = parser.parse_args()
    expected = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_WORKFLOW": "Release", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/release.yml@refs/heads/main",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise ValueError("Authorize releases only through the Release workflow on main")
    commit = authorize_release(args.tag, args.commit, os.environ["GITHUB_SHA"])
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"commit={commit}\n")


if __name__ == "__main__":
    main()
