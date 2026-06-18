# Release Security Review

Date: 2026-06-18

This repository was prepared for public GitHub sharing with the following hygiene checks:

- Removed Python bytecode and `__pycache__` directories.
- Confirmed local runtime artifacts such as `livefirettx.db` and `generated/` are excluded by `.gitignore` and not present in the packaged repository.
- Scanned for obvious secrets and sensitive patterns, including common API keys, AWS keys, GitHub tokens, Slack tokens, private-key headers, password/token/secret assignments, private local paths, and unrelated internal project references.
- Updated the license summary to reference LiveFireTTX and substantially similar live-fire tabletop / exercise orchestration products rather than unrelated project names.
- Confirmed the Python package compiles successfully.

No obvious secrets, tokens, private endpoints, local filesystem paths, or unrelated internal project references were found by the scan performed during packaging.

This review is a best-effort packaging hygiene check, not a legal review or a substitute for a dedicated secret-scanning tool in CI/CD.
