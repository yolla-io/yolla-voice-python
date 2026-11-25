from pathlib import Path

import pytest

from scripts.check_gen import STALE_MESSAGE, check_generated
from scripts.generate_models import generate_models

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "openapi" / "reseller-api.yaml"


def test_check_gen_reports_changed_byte(tmp_path):
    output = tmp_path / "generated"
    generate_models(source=_SOURCE, output=output)
    generated_file = output / "models.py"
    generated_file.write_bytes(generated_file.read_bytes() + b"\n")

    with pytest.raises(RuntimeError, match=f"^{STALE_MESSAGE}$"):
        check_generated(source=_SOURCE, output=output)


def test_check_gen_accepts_unchanged_copy(tmp_path):
    output = tmp_path / "generated"
    generate_models(source=_SOURCE, output=output)

    check_generated(source=_SOURCE, output=output)


def test_check_gen_reports_missing_file(tmp_path):
    output = tmp_path / "generated"
    generate_models(source=_SOURCE, output=output)
    (output / "__init__.py").unlink()

    with pytest.raises(RuntimeError, match=f"^{STALE_MESSAGE}$"):
        check_generated(source=_SOURCE, output=output)


def test_check_gen_reports_extra_file(tmp_path):
    output = tmp_path / "generated"
    generate_models(source=_SOURCE, output=output)
    (output / "unexpected.py").write_text("# Unexpected output\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=f"^{STALE_MESSAGE}$"):
        check_generated(source=_SOURCE, output=output)
