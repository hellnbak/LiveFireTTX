# Contributing

Thanks for your interest in LiveFireTTX.

Contributions must preserve the v1 safety contract: simulate symptoms and
operational pressure, but do not add malware, exploit tooling, credential theft,
persistence, evasion, anti-forensics, or destructive behavior.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
uvicorn app.main:app --reload
```

## Contribution guidelines

- Keep chaos actions safe, reversible, and clearly marked as simulated.
- Prefer structured scenario definitions over hard-coded one-off behavior.
- Include cleanup behavior for generated environments.
- Do not commit generated exercise packages, local databases, secrets, or logs.
- Update docs when changing user-facing behavior.
- Add tests for migrations, generated packages, safety boundaries, and routes.
- Run `make release-check` before opening a pull request.
