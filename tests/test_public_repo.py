import pytest


def test_public_guard_rejects_cyrillic_and_internal_host():
    from scripts.check_public import find_forbidden

    assert "Cyrillic text" in find_forbidden("\u043f\u0440\u0438\u0432\u0435\u0442")
    assert "internal host" in find_forbidden("et" + "service.example")
    assert "project repository reference" in find_forbidden(
        "../" + "platform" + "-api/api/openapi.yaml"
    )


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("https://" + "con" + "fluence.example/wiki", "wiki link"),
        ("https://" + "at" + "lassian.example", "wiki vendor"),
        ("security@" + "yollacalls.com", "internal email"),
        ("http://" + "local" + "host:8080/docs", "local dev URL"),
        ("platform" + "-billing", "project repository reference"),
        ("platform" + "-specs", "project repository reference"),
        ("platform" + "-sdk-nodejs", "project repository reference"),
        ("platform" + "-sdk-golang", "project repository reference"),
        ("platform" + "-admin-ui", "project repository reference"),
        ("platform" + "-client-ui", "project repository reference"),
        ("yolla-voice" + "-ios-sdk", "project repository reference"),
    ],
)
def test_public_guard_rejects_private_content(text, rule):
    from scripts.check_public import find_forbidden

    assert rule in find_forbidden(text)


def test_public_guard_accepts_ordinary_english_documentation():
    from scripts.check_public import find_forbidden

    text = """# Yolla Voice Python SDK

Install the package, configure an API key, and create calls from your server.
See the API documentation for pagination, retries, and signed webhook examples.
"""
    assert find_forbidden(text) == []


def test_public_guard_scans_clean_tracked_files(capsys):
    from scripts.check_public import main

    assert main() == 0
    assert "tracked files clean" in capsys.readouterr().out
