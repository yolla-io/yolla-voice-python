import json
from collections.abc import Mapping
from typing import Any

from yolla_voice.errors import YollaVoiceError


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered_name:
            return value
    return None


def decode_body(status: int, headers: Mapping[str, str], content: bytes) -> Any:
    if not content:
        return None

    content_type = _header(headers, "Content-Type")
    if content_type is None:
        return None

    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != "application/json" and not media_type.endswith("+json"):
        return None

    try:
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        if status >= 400:
            return None
        raise YollaVoiceError(
            "Invalid JSON response",
            code="invalid_response",
            status=status,
            request_id=_header(headers, "X-Request-Id"),
        ) from None


def _validate_random_value(random_value: float) -> None:
    if not 0.0 <= random_value <= 1.0:
        raise ValueError("random_value must be between 0 and 1")


def backoff_delay(attempt: int, random_value: float) -> float:
    _validate_random_value(random_value)
    ceiling: float = min(8, 0.5 * 2**attempt)
    return random_value * ceiling


def retry_delay(
    attempt: int,
    retry_after: float | None,
    random_value: float,
) -> float:
    _validate_random_value(random_value)
    if retry_after is not None:
        return min(retry_after, 60)
    return backoff_delay(attempt, random_value)
