from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".release-smoke",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "backups",
    "build",
    "dist",
    "generated",
    "livefirettx.egg-info",
}
PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----"),
)


def candidate_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    ]


def main() -> int:
    findings: list[Path] = []
    for path in candidate_files():
        content = path.read_bytes()
        if b"\0" in content:
            continue
        text = content.decode("utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in PATTERNS):
            findings.append(path.relative_to(ROOT))

    if findings:
        print("Potential secret pattern found in:")
        for path in findings:
            print(path)
        return 1

    print("Secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
