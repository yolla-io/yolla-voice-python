"""Check an installed yolla-voice-python distribution, not the source checkout.

Run against a built wheel with:

    uv run --isolated --no-project --with dist/*.whl python scripts/smoke_test.py
"""

import importlib.metadata
import importlib.resources
import sys
from pathlib import Path

import yolla_voice
from yolla_voice import AsyncYollaVoice, YollaVoice, sign_webhook, verify_webhook

_SOURCE_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "yolla_voice"


def main() -> int:
    package_dir = Path(yolla_voice.__file__).resolve().parent
    if package_dir == _SOURCE_PACKAGE:
        print("smoke test imported the source checkout, not the installed wheel", file=sys.stderr)
        return 1
    installed = importlib.metadata.version("yolla-voice-python")
    assert yolla_voice.__version__ == installed, (yolla_voice.__version__, installed)
    assert importlib.resources.files("yolla_voice").joinpath("py.typed").is_file()

    signed = sign_webhook(
        b'{"id":"evt_smoke","type":"webhook.test","seq":0,"createdAt":"2026-01-01T00:00:00Z","data":{}}',
        secret="smoke-secret",
    )
    event = verify_webhook(signed.body, signed.headers, secret="smoke-secret")
    assert event.type == "webhook.test"

    for client_type in (YollaVoice, AsyncYollaVoice):
        assert "smoke-key" not in repr(client_type(api_key="smoke-key"))

    print(f"yolla-voice-python {yolla_voice.__version__} installed at {package_dir}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
