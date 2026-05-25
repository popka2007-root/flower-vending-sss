"""Fail when generated artifacts or local-machine paths are tracked."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATH_PARTS = {
    ".pytest_cache",
    "__pycache__",
    "artifacts",
    "var",
}
FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".docx",
}
TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".desktop",
    ".iss",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SELF_PATH = Path("scripts/check_repository_hygiene.py")
FORBIDDEN_TEXT_PATTERNS = {
    r"C:\Users\User\Downloads\flower-vending-system": "machine-local checkout path",
    r"C:\Users\User\Desktop\flower-vending-system": "machine-local checkout path",
    "/C:/Users/User/Desktop/flower-vending-system": "machine-local markdown link",
    "src/flower_vending/infrastructure/platform": "stale platform package path",
    "target-192-168-1-74-assessment": "private target address in public filename/link",
    "192.168.1.74": "private target address in tracked text",
    "vending@192.168.1.74": "private target account/address in tracked text",
}


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def check_paths(paths: list[Path]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        relative = path.relative_to(ROOT)
        parts = set(relative.parts)
        if parts & FORBIDDEN_PATH_PARTS:
            violations.append(f"tracked generated path: {relative.as_posix()}")
            continue
        if relative.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(f"tracked generated/binary artifact: {relative.as_posix()}")
    return violations


def check_text(paths: list[Path]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        relative = path.relative_to(ROOT)
        if relative == SELF_PATH:
            continue
        if relative.suffix.lower() not in TEXT_SUFFIXES or not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"non-UTF-8 tracked text candidate: {relative.as_posix()}")
            continue
        for pattern, reason in FORBIDDEN_TEXT_PATTERNS.items():
            if pattern in text:
                violations.append(f"{relative.as_posix()}: contains {reason}")
    return violations


def main() -> int:
    paths = repository_files()
    violations = check_paths(paths) + check_text(paths)
    if violations:
        print("Repository hygiene check failed:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("PASS: repository hygiene check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
