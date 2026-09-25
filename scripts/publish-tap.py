#!/usr/bin/env python3
"""Update only this cask through GitHub's optimistic-concurrency Contents API."""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from release import check_tag

URL = "https://api.github.com/repos/agrechin/homebrew-tap/contents/Casks/unrar.rb"


def request(method, payload=None):
    req = urllib.request.Request(
        URL + ("?ref=main" if method == "GET" else ""), method=method,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": "Bearer " + os.environ["HOMEBREW_TAP_TOKEN"],
                 "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if method == "GET" and error.code == 404:
            return None
        raise


def main():
    tag, path = sys.argv[1:]
    check_tag(tag)
    content = Path(path).read_bytes()
    old = request("GET")
    if old and base64.b64decode(old["content"]) == content:
        print("Homebrew cask already matches this release.")
        return
    payload = {"message": f"chore: update UnRAR cask to {tag}", "branch": "main",
               "content": base64.b64encode(content).decode()}
    if old:
        payload["sha"] = old["sha"]
    request("PUT", payload)
    current = request("GET")
    if not current or base64.b64decode(current["content"]) != content:
        raise SystemExit("Homebrew cask readback did not match")
    print("Updated https://github.com/agrechin/homebrew-tap/blob/main/Casks/unrar.rb")


if __name__ == "__main__":
    main()
