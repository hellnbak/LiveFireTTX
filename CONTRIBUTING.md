# Contributing

Thanks for your interest in LiveFireTTX.

This project is an MVP. Contributions should preserve the safety model: simulate symptoms and operational pressure, but do not add malware, exploit tooling, credential theft, persistence, evasion, anti-forensics, or destructive behavior.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Contribution guidelines

- Keep chaos actions safe, reversible, and clearly marked as simulated.
- Prefer structured scenario definitions over hard-coded one-off behavior.
- Include cleanup behavior for generated environments.
- Do not commit generated exercise packages, local databases, secrets, or logs.
- Update docs when changing user-facing behavior.
