from dataclasses import FrozenInstanceError

import pytest

from yolla_voice._http.common import backoff_delay, decode_body, retry_delay
from yolla_voice._http.types import HttpResponse, RequestSpec
from yolla_voice.errors import YollaVoiceError


def test_request_spec_defaults_and_values():
    request = RequestSpec(method="GET", path="/calls")

    assert request.method == "GET"
    assert request.path == "/calls"
    assert request.query is None
    assert request.body is None
    assert request.headers is None
    assert request.retryable is True


def test_request_spec_is_frozen():
    request = RequestSpec(method="GET", path="/calls")

    with pytest.raises(FrozenInstanceError):
        request.method = "POST"  # type: ignore[misc]


def test_http_response_preserves_generic_data_and_metadata():
    response = HttpResponse[str](
        data="created",
        status=201,
        headers={"X-Request-Id": "request-1"},
    )

    assert response.data == "created"
    assert response.status == 201
    assert response.headers == {"X-Request-Id": "request-1"}


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/problem+json",
        "application/vnd.api+json; charset=utf-8",
        "APPLICATION/JSON; CHARSET=UTF-8",
    ],
)
def test_decode_body_parses_json_content_types(content_type):
    body = decode_body(200, {"Content-Type": content_type}, b'{"ok":true}')

    assert body == {"ok": True}


@pytest.mark.parametrize(
    ("headers", "content"),
    [
        ({"Content-Type": "application/json"}, b""),
        ({}, b'{"ok":true}'),
        ({"Content-Type": "text/plain"}, b'{"ok":true}'),
    ],
)
def test_decode_body_returns_none_for_empty_or_non_json_bodies(headers, content):
    assert decode_body(200, headers, content) is None


@pytest.mark.parametrize("status", [400, 500])
def test_decode_body_returns_none_for_malformed_error_json(status):
    body = decode_body(
        status,
        {"Content-Type": "application/json"},
        b'{"error":',
    )

    assert body is None


def test_decode_body_rejects_malformed_success_json_without_exposing_body():
    secret = b'{"apiKey":"response-body-secret"'

    with pytest.raises(YollaVoiceError) as caught:
        decode_body(
            200,
            {
                "Content-Type": "application/json",
                "x-rEqUeSt-Id": "request-1",
            },
            secret,
        )

    error = caught.value
    assert error.code == "invalid_response"
    assert error.status == 200
    assert error.request_id == "request-1"
    assert "response-body-secret" not in str(error)
    assert "response-body-secret" not in repr(error)
    assert error.__cause__ is None


def test_backoff_delay_uses_full_jitter_from_half_a_second():
    assert backoff_delay(0, 0.5) == 0.25
    assert backoff_delay(2, 0.25) == 0.5


def test_backoff_delay_caps_the_exponential_ceiling_at_eight_seconds():
    assert backoff_delay(10, 1.0) == 8.0
    assert backoff_delay(10, 0.5) == 4.0


def test_retry_delay_falls_back_to_backoff_without_retry_after():
    assert retry_delay(0, None, 0.5) == 0.25


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [(0.0, 0.0), (12.5, 12.5), (120.0, 60.0)],
)
def test_retry_delay_replaces_backoff_with_capped_retry_after(retry_after, expected):
    assert retry_delay(4, retry_after, 1.0) == expected


@pytest.mark.parametrize("random_value", [-0.01, 1.01, float("nan")])
def test_retry_helpers_reject_random_values_outside_unit_interval(random_value):
    with pytest.raises(ValueError, match="random_value"):
        backoff_delay(0, random_value)

    with pytest.raises(ValueError, match="random_value"):
        retry_delay(0, 1.0, random_value)
