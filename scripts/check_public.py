import re
import subprocess
import sys
from pathlib import Path

_PROJECT_REPOSITORIES = (
    "client-api-example",
    "platform-admin-ui",
    "platform-api",
    "platform-billing",
    "platform-client-ui",
    "platform-sdk-golang",
    "platform-sdk-nodejs",
    "platform-specs",
    "yolla-voice-ios-sdk",
)

_FORBIDDEN = (
    ("internal host", re.compile(r"etservice", re.IGNORECASE)),
    ("wiki link", re.compile(r"confluence", re.IGNORECASE)),
    ("wiki vendor", re.compile(r"atlassian", re.IGNORECASE)),
    ("internal email", re.compile(r"@yollacalls\.com", re.IGNORECASE)),
    ("local dev URL", re.compile(r"localhost:8080")),
    ("Cyrillic text", re.compile(r"[\u0400-\u04ff\u0500-\u052f\u2de0-\u2dff\ua640-\ua69f]")),
    (
        "project repository reference",
        re.compile("|".join(re.escape(name) for name in _PROJECT_REPOSITORIES), re.IGNORECASE),
    ),
)

_ROOT = Path(__file__).resolve().parents[1]
_GUARD_PATH = "scripts/check_public.py"


def find_forbidden(text: str) -> list[str]:
    return [name for name, pattern in _FORBIDDEN if pattern.search(text)]


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [path for path in result.stdout.split("\0") if path and path != _GUARD_PATH]


def main() -> int:
    files = _tracked_files()
    failed = False
    for file in files:
        text = (_ROOT / file).read_text(encoding="utf-8")
        for finding in find_forbidden(text):
            print(f"{file}: {finding}", file=sys.stderr)
            failed = True
    if failed:
        return 1
    print(f"Public-repo guard: {len(files)} tracked files clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
