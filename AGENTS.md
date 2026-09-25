# Repository guidance

- Keep RARLAB source and its license intact; scope build-tool changes to tooling.
- `bash scripts/check.sh` is the Docker validation gate. On Apple Silicon also
  run `bash scripts/build.sh` and `python3 scripts/smoke.py .build/macos/unrar`.
- Builds target macOS arm64 only. SDK 26.5 is intentional: LLVM 21 cannot parse
  SDK 27's new architecture stubs. Do not silently patch SDK files.
- Never commit or publish Apple SDKs, private keys, P12 files, or keychains.
- Release signing and notarization must fail closed; never strip quarantine.
- Never route pull-request code to the self-hosted signing runner.
- Keep release tags aligned with `version.hpp`, including beta status.
- Preserve published release bytes. Retry only failed publication jobs to finish
  a tap update using the original signed workflow artifact.
- Use Conventional Commits. Keep single-commit changes on main; rebase branches
  onto the base, never merge the base into a working branch.
