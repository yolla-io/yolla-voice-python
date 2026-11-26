import importlib.metadata

import yolla_voice


def test_initial_version():
    assert yolla_voice.__version__ == "0.1.0"
    assert importlib.metadata.version("yolla-voice-python") == yolla_voice.__version__


def test_sdist_ships_only_an_explicit_allowlist():
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    )
    included = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]

    assert not [path for path in included if path.startswith(".")]
    assert {"src", "README.md", "LICENSE"} <= set(included)
