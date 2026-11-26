from datetime import UTC, datetime, timedelta

import pytest

from yolla_voice.errors import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    ConflictError,
    InsufficientBalanceError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    ValidationError,
    WebhookVerificationError,
    YollaVoiceError,
    error_from_response,
    parse_retry_after,
)


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, ValidationError),
        (422, ValidationError),
        (401, AuthenticationError),
        (402, InsufficientBalanceError),
        (403, PermissionError),
        (404, NotFoundError),
        (409, ConflictError),
        (429, RateLimitError),
        (500, ServerError),
        (418, YollaVoiceError),
    ],
)
def test_error_from_response_maps_status(status, error_type):
    error = error_from_response(
        status,
        {"error": {"code": "request_failed", "message": "Request failed"}},
        {},
    )

    assert type(error) is error_type
    assert isinstance(error, YollaVoiceError)
    assert error.status == status
    assert error.code == "request_failed"
    assert str(error) == "Request failed"


def test_error_from_response_uses_body_request_id_before_header():
    error = error_from_response(
        400,
        {
            "error": {
                "code": "invalid_request",
                "message": "Invalid request",
                "requestId": "body-request-id",
            }
        },
        {"X-Request-Id": "header-request-id"},
    )

    assert error.request_id == "body-request-id"


def test_error_from_response_uses_case_insensitive_header_request_id_fallback():
    error = error_from_response(
        400,
        {"error": {"code": "invalid_request", "message": "Invalid request"}},
        {"x-rEqUeSt-Id": "header-request-id"},
    )

    assert error.request_id == "header-request-id"


@pytest.mark.parametrize(
    "body",
    [
        None,
        "raw response secret",
        [],
        {},
        {"error": None},
        {"error": "invalid"},
        {"error": {"message": "Missing code"}},
        {"error": {"code": "missing_message"}},
        {"error": {"code": 123, "message": "Invalid code"}},
        {"error": {"code": "invalid_message", "message": 123}},
    ],
)
def test_malformed_error_body_uses_generic_unknown_error(body):
    error = error_from_response(503, body, {})

    assert type(error) is ServerError
    assert error.code == "unknown_error"
    assert str(error) == "HTTP 503"


def test_error_string_and_repr_do_not_expose_response_secrets():
    error = error_from_response(
        401,
        {
            "error": {
                "code": "unauthorized",
                "message": "Authentication failed",
                "requestId": "request-id",
            },
            "apiKey": "response-api-key-secret",
        },
        {
            "Authorization": "Bearer authorization-secret",
            "X-Request-Id": "header-request-id",
        },
    )

    for rendered in (str(error), repr(error)):
        assert "response-api-key-secret" not in rendered
        assert "authorization-secret" not in rendered
        assert "Bearer" not in rendered


def test_malformed_error_does_not_expose_raw_body():
    error = error_from_response(500, "response-body-secret", {})

    assert "response-body-secret" not in str(error)
    assert "response-body-secret" not in repr(error)


def test_rate_limit_error_parses_retry_after_case_insensitively():
    error = error_from_response(
        429,
        {"error": {"code": "rate_limited", "message": "Slow down"}},
        {"rEtRy-AfTeR": "2.5"},
    )

    assert isinstance(error, RateLimitError)
    assert error.retry_after == 2.5


def test_rate_limit_error_retry_after_defaults_to_none():
    error = RateLimitError("Slow down", code="rate_limited", status=429)

    assert error.retry_after is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("not-a-delay", None),
        ("NaN", None),
        ("inf", None),
        ("0", 0.0),
        ("2.5", 2.5),
        ("-3", 0.0),
    ],
)
def test_parse_retry_after_seconds(value, expected):
    assert parse_retry_after(value) == expected


def test_parse_retry_after_http_date_uses_timezone_aware_difference():
    now = datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC)

    assert parse_retry_after("Wed, 15 Nov 2023 22:13:35 GMT", now=now) == 15.0


def test_parse_retry_after_http_date_accepts_naive_now_as_utc():
    now = datetime(2023, 11, 15, 22, 13, 20)

    assert parse_retry_after("Wed, 15 Nov 2023 22:13:35 GMT", now=now) == 15.0


def test_parse_retry_after_http_date_supports_offsets_and_fractional_seconds():
    now = datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC)

    value = "Thu, 16 Nov 2023 00:13:35 +0200"
    assert parse_retry_after(value, now=now + timedelta(microseconds=500000)) == 14.5


def test_parse_retry_after_clamps_past_http_date_to_zero():
    now = datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC)

    assert parse_retry_after("Wed, 15 Nov 2023 22:13:00 GMT", now=now) == 0.0


@pytest.mark.parametrize(
    "value", ["Wed, 99 Nov 2023 22:13:35 GMT", "Wed, 15 Nov 2023 25:13:35 GMT"]
)
def test_parse_retry_after_returns_none_for_invalid_http_date(value):
    assert parse_retry_after(value) is None


def test_connection_error_preserves_cause_without_copying_its_message():
    original = OSError("socket-password-secret")

    try:
        try:
            raise original
        except OSError as exc:
            raise APIConnectionError() from exc
    except APIConnectionError as error:
        assert error.__cause__ is original
        assert error.status is None
        assert error.request_id is None
        assert "socket-password-secret" not in str(error)
        assert "socket-password-secret" not in repr(error)


def test_timeout_error_is_an_sdk_error_with_safe_message():
    error = APITimeoutError()

    assert isinstance(error, YollaVoiceError)
    assert isinstance(error, APIConnectionError)
    assert error.status is None
    assert str(error) == "Request timed out"


@pytest.mark.parametrize(
    "reason", ["missing_header", "bad_signature", "stale_timestamp", "invalid_payload"]
)
def test_webhook_verification_error_exposes_reason(reason):
    error = WebhookVerificationError(reason=reason)

    assert isinstance(error, YollaVoiceError)
    assert error.reason == reason
    assert error.status is None
    assert "webhook-signature-secret" not in str(error)
    assert "webhook-signing-secret" not in repr(error)
