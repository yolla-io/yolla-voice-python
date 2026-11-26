import hmac
import json
import math
import time
from collections.abc import Mapping
from typing import Any, NoReturn

from pydantic import ValidationError

from ..errors import WebhookVerificationError
from .events import WebhookEvent, parse_event
from .headers import SIGNATURE_HEADER, TIMESTAMP_HEADER, get_header
from .secret import WebhookSecret, resolve_webhook_secret
from .sign import compute_signature

DEFAULT_TOLERANCE = 300.0
_HEX_DIGITS = frozenset("0123456789abcdef")


def _raw_body_bytes(raw_body: bytes | str) -> bytes:
    if isinstance(raw_body, bytes):
        return raw_body
    if isinstance(raw_body, str):
        return raw_body.encode("utf-8")
    raise TypeError("Webhook body must be raw request bytes or a UTF-8 string, not a parsed value")


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError("Invalid JSON constant")


def _invalid_event() -> NoReturn:
    raise WebhookVerificationError("Webhook body is not a valid event", reason="invalid_payload")


def verify_webhook(
    raw_body: bytes | str,
    headers: Mapping[str, str],
    *,
    secret: WebhookSecret | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
    now: float | None = None,
) -> WebhookEvent:
    secrets = resolve_webhook_secret(secret)
    body = _raw_body_bytes(raw_body)
    if tolerance < 0 or not math.isfinite(tolerance):
        raise ValueError("tolerance must be a non-negative finite number")

    timestamp = (get_header(headers, TIMESTAMP_HEADER) or "").strip()
    signature = (get_header(headers, SIGNATURE_HEADER) or "").strip()
    if not timestamp or not signature:
        raise WebhookVerificationError(
            f"Missing {TIMESTAMP_HEADER} or {SIGNATURE_HEADER} header", reason="missing_header"
        )
    if not timestamp.isascii() or not timestamp.isdigit():
        raise WebhookVerificationError(
            f"Invalid {TIMESTAMP_HEADER} header", reason="missing_header"
        )

    try:
        timestamp_value = int(timestamp)
        current_time = time.time() if now is None else now
        stale = abs(current_time - timestamp_value) > tolerance
    except (OverflowError, ValueError):
        stale = True
    if stale:
        raise WebhookVerificationError(
            "Webhook timestamp is outside the allowed tolerance", reason="stale_timestamp"
        )

    received = signature[3:] if signature.startswith("v1=") else ""
    if len(received) != 64 or any(character not in _HEX_DIGITS for character in received):
        raise WebhookVerificationError("Webhook signature does not match", reason="bad_signature")

    received_bytes = received.encode("ascii")
    matches = False
    for candidate in secrets:
        expected = compute_signature(candidate, timestamp, body).encode("ascii")
        matches = hmac.compare_digest(expected, received_bytes) or matches
    if not matches:
        raise WebhookVerificationError("Webhook signature does not match", reason="bad_signature")

    try:
        payload: Any = json.loads(body.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise WebhookVerificationError(
            "Webhook body is not valid JSON", reason="invalid_payload"
        ) from None
    if not isinstance(payload, Mapping):
        _invalid_event()
    try:
        return parse_event(payload)
    except (ValidationError, TypeError, ValueError):
        raise WebhookVerificationError(
            "Webhook body is not a valid event", reason="invalid_payload"
        ) from None
