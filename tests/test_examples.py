import ast
import re
import runpy
from pathlib import Path

import pytest

import yolla_voice
import yolla_voice.webhooks

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*.py"))
README = ROOT / "README.md"
FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)
PUBLIC_MODULES = {"yolla_voice": yolla_voice, "yolla_voice.webhooks": yolla_voice.webhooks}


def readme_blocks() -> list[str]:
    return FENCE.findall(README.read_text(encoding="utf-8"))


def imported_names(source: str) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module in PUBLIC_MODULES:
            names.extend((node.module, alias.name) for alias in node.names)
    return names


def test_expected_examples_exist():
    assert {path.name for path in EXAMPLES} == {
        "sync_quickstart.py",
        "async_quickstart.py",
        "asgi_webhooks.py",
        "wsgi_webhooks.py",
    }


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_imports_without_running_main(path, monkeypatch):
    monkeypatch.setenv("YOLLA_API_KEY", "placeholder-api-key")
    monkeypatch.setenv("YOLLA_WEBHOOK_SECRET", "placeholder-webhook-secret")

    namespace = runpy.run_path(str(path), run_name="example_import_test")

    assert callable(namespace.get("main")) or callable(namespace.get("app"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_imports_exist(path):
    for module, name in imported_names(path.read_text(encoding="utf-8")):
        assert hasattr(PUBLIC_MODULES[module], name), f"{module}.{name}"


def test_readme_has_python_examples():
    assert len(readme_blocks()) >= 10


@pytest.mark.parametrize("index", range(len(FENCE.findall(README.read_text(encoding="utf-8")))))
def test_readme_block_compiles_and_imports_exist(index):
    source = readme_blocks()[index]
    compile(source, f"README.md block {index}", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    for module, name in imported_names(source):
        assert hasattr(PUBLIC_MODULES[module], name), f"{module}.{name}"


def test_readme_webhook_test_snippet_runs():
    source = next(
        block for block in readme_blocks() if "sign_webhook(" in block and "handle(" in block
    )
    exec(compile(source, "README.md webhook test", "exec"), {})  # noqa: S102
