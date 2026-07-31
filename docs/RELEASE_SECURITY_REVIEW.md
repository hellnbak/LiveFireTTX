# Release Security Review

Date: 2026-07-30

The v1.0 release candidate was prepared with the following controls:

- Removed Python bytecode and `__pycache__` directories.
- Confirmed local runtime artifacts such as `livefirettx.db` and `generated/` are excluded by `.gitignore` and not present in the packaged repository.
- Scanned for obvious secrets and sensitive patterns, including common API keys, AWS keys, GitHub tokens, Slack tokens, private-key headers, password/token/secret assignments, private local paths, and unrelated internal project references.
- Updated the license summary to reference LiveFireTTX and substantially similar live-fire tabletop / exercise orchestration products rather than unrelated project names.
- Confirmed the Python package compiles successfully.
- Added path-contained, schema-aware backup and restore validation.
- Added localhost-only controller configuration validation.
- Added trusted-host, same-origin mutation, and browser security-header
  enforcement for the facilitator interface.
- Added CI lint, type, coverage, dependency audit, secret scan, package-build,
  generated Docker smoke, and CodeQL workflows.
- Added a documented threat model and release checklist.
- Removed the multipart runtime dependency and upgraded all runtime pins to the
  newest published compatible releases.
- Documented the temporary Starlette upstream exceptions whose fixes require a
  version outside FastAPI's published compatibility range.

No obvious secrets, tokens, private endpoints, local filesystem paths, or unrelated internal project references were found by the scan performed during packaging.

This review is a best-effort engineering review, not a legal review. Final
publication still requires the automated release checklist and GitHub security
results to pass.
