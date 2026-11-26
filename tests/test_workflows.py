from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
SUPPORTED_PYTHONS = ["3.11", "3.12", "3.13", "3.14", "3.15"]


def load(name: str) -> dict[str, Any]:
    document: dict[Any, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML reads the bare `on` key as the boolean True.
    document["on"] = document.pop(True, document.get("on"))
    return document


def commands(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


def all_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_ci_runs_on_pull_requests_and_main_pushes():
    triggers = load("ci.yml")["on"]

    assert "pull_request" in triggers
    assert triggers["push"]["branches"] == ["main"]


def test_ci_matrix_is_exactly_the_supported_pythons():
    job = load("ci.yml")["jobs"]["test"]

    assert job["strategy"]["matrix"]["python-version"] == SUPPORTED_PYTHONS


def test_ci_runs_every_quality_gate():
    job = load("ci.yml")["jobs"]["test"]
    run = "\n".join(commands(job))

    for command in (
        "uv sync --locked",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src tests",
        "uv run coverage run -m pytest",
        "uv run coverage report",
        "uv run python scripts/check_gen.py",
        "uv run python scripts/check_public.py",
        "uv build",
    ):
        assert command in run, command


def test_ci_runs_newest_only_checks_once():
    job = load("ci.yml")["jobs"]["test"]
    newest = f"matrix.python-version == '{SUPPORTED_PYTHONS[-1]}'"
    once = ("check_gen.py", "check_public.py", "uv build")

    for step in job["steps"]:
        if any(marker in step.get("run", "") for marker in once):
            assert step.get("if") == newest, step["run"]


def test_release_triggers_on_version_tags_only():
    triggers = load("release.yml")["on"]

    assert triggers == {"push": {"tags": ["v*"]}}


def test_release_uses_trusted_publishing_with_minimal_permissions():
    workflow = load("release.yml")
    publish = workflow["jobs"]["publish"]

    assert workflow["permissions"] == {"contents": "read"}
    assert publish["permissions"] == {"id-token": "write", "contents": "read"}
    assert publish["needs"] == "build"
    assert any(
        step.get("uses", "").startswith("pypa/gh-action-pypi-publish@") for step in publish["steps"]
    )


def test_no_long_lived_publishing_token_is_referenced():
    for name in ("ci.yml", "release.yml"):
        text = all_text(name).lower()
        assert "password" not in text
        assert "pypi_token" not in text
        assert "secrets." not in text


def test_release_verifies_and_smoke_tests_before_publishing():
    build = load("release.yml")["jobs"]["build"]
    run = "\n".join(commands(build))

    for command in (
        "uv sync --locked",
        'test "$GITHUB_REF_NAME" = "v$version"',
        "uv run mypy src tests",
        "uv run coverage run -m pytest",
        "uv run python scripts/check_gen.py",
        "uv run python scripts/check_public.py",
        "uv build",
        "uv run --isolated --no-project --with dist/*.whl",
    ):
        assert command in run, command
