import argparse
import sys
import tempfile
from pathlib import Path

if __package__ == "scripts":
    from scripts.generate_models import generate_models
else:  # executed as `python scripts/check_gen.py`
    from generate_models import generate_models  # type: ignore[import-not-found,no-redef]

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "openapi" / "reseller-api.yaml"
_OUTPUT = _ROOT / "src" / "yolla_voice" / "generated"
STALE_MESSAGE = "Generated models are stale: run scripts/generate_models.py"


def _generated_files(directory: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(directory): path.read_bytes()
        for path in directory.rglob("*.py")
        if path.is_file()
    }


def check_generated(source: Path = _SOURCE, output: Path = _OUTPUT) -> None:
    with tempfile.TemporaryDirectory(prefix="yolla-voice-models-") as temporary_directory:
        regenerated = Path(temporary_directory) / "generated"
        generate_models(source=source, output=regenerated)
        expected = _generated_files(regenerated)
    actual = _generated_files(output)
    if actual != expected:
        raise RuntimeError(STALE_MESSAGE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that committed generated models are fresh")
    parser.add_argument("--source", type=Path, default=_SOURCE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    args = parser.parse_args(argv)
    try:
        check_generated(source=args.source, output=args.output)
    except RuntimeError as error:
        if str(error) != STALE_MESSAGE:
            raise
        print(STALE_MESSAGE, file=sys.stderr)
        return 1
    print("Generated models are fresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
