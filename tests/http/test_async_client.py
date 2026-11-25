import asyncio
import json
import platform

import httpx
import pytest

import yolla_voice._http.client as client_module
from yolla_voice import __version__
from yolla_voice._http.client import AsyncHttpClient, HttpConfig
from yolla_voice._http.types import RequestSpec
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
    YollaVoiceError,
)

API_KEY = "test-api-key-secret"
BASE_URL = "https://api.example.com/platform/v1/"
RESPONSE_SECRET = "response-body-secret"


def json_response(status, body=None, *, request_id=None, headers=None):
    response_headers = dict(headers or {})
    if body is not None:
        response_headers["Content-Type"] = "application/json"
    if request_id is not None:
        response_headers["X-Request-Id"] = request_id
    content = b"" if body is None else json.dumps(body).encode()
    return httpx.Response(status, content=content, headers=response_headers)


def error_body(message="Request failed"):
    return {
        "error": {"code": "request_failed", "message": message},
        "secret": RESPONSE_SECRET,
    }


@pytest.fixture(autouse=True)
def no_real_delays(monkeypatch):
    async def unexpected_sleep(delay):
        pytest.fail(f"unexpected real sleep: {delay}")

    monkeypatch.setattr(client_module, "async_sleep", unexpected_sleep)
    monkeypatch.setattr(client_module, "random", lambda: 0.5)


@pytest.fixture
async def client_factory():
    clients = []

    def factory(handler, **config_overrides):
        config = HttpConfig(
            api_key=API_KEY,
            base_url=config_overrides.pop("base_url", BASE_URL),
            **config_overrides,
        )
        client = AsyncHttpClient(config, transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_request_builds_headers_url_query_and_json_body(client_factory):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, {"ok": True})

    client = client_factory(handler)
    body = {"destination": "15551234567"}
    response = await client.request(
        RequestSpec(
            method="POST",
            path="/calls",
            query={"externalUserId": "user A", "cursor": "a/b", "limit": 10},
            body=body,
            headers={"Idempotency-Key": "order-A-1001"},
        )
    )

    assert response.data == {"ok": True}
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == (
        "https://api.example.com/platform/v1/calls?externalUserId=user+A&cursor=a%2Fb&limit=10"
    )
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Idempotency-Key"] == "order-A-1001"
    assert f"yolla-voice-python/{__version__}" in request.headers["User-Agent"]
    assert platform.python_version() in request.headers["User-Agent"]
    assert json.loads(request.content) == body


async def test_bodyless_request_has_no_json_content_type(client_factory):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200)

    client = client_factory(handler)
    await client.request(RequestSpec("GET", "calls"))

    assert "Content-Type" not in seen[0].headers
    assert seen[0].content == b""


@pytest.mark.parametrize("status", [200, 201, 202])
async def test_successful_json_statuses_return_data_and_metadata(client_factory, status):
    def handler(request):
        return json_response(
            status,
            {"status": "accepted"},
            request_id="request-success",
            headers={"X-Extra": "metadata"},
        )

    client = client_factory(handler)
    response = await client.request(RequestSpec("POST", "/calls", body={}))

    assert response.status == status
    assert response.data == {"status": "accepted"}
    assert response.headers["X-Request-Id"] == "request-success"
    assert response.headers["X-Extra"] == "metadata"


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
        (503, ServerError),
        (418, YollaVoiceError),
    ],
)
async def test_http_errors_are_typed_and_do_not_leak_raw_body(client_factory, status, error_type):
    calls = []

    def handler(request):
        calls.append(request)
        return json_response(status, error_body(), request_id="request-error")

    client = client_factory(handler, max_retries=0)
    with pytest.raises(error_type) as caught:
        await client.request(RequestSpec("GET", "/calls"))

    error = caught.value
    assert error.status == status
    assert error.code == "request_failed"
    assert error.request_id == "request-error"
    assert RESPONSE_SECRET not in str(error)
    assert RESPONSE_SECRET not in repr(error)
    assert len(calls) == 1


@pytest.mark.parametrize(("status", "retryable"), [(400, True), (500, False)])
async def test_nonretryable_response_and_spec_stop_after_one_attempt(
    client_factory, status, retryable
):
    calls = []

    def handler(request):
        calls.append(request)
        return json_response(status, error_body())

    client = client_factory(handler)
    with pytest.raises(YollaVoiceError):
        await client.request(RequestSpec("GET", "/calls", retryable=retryable))

    assert len(calls) == 1


async def test_429_retries_honor_retry_after_and_raise_final_attempt(client_factory, monkeypatch):
    calls = []
    delays = []

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(client_module, "async_sleep", record_sleep)

    def handler(request):
        calls.append(request)
        return json_response(
            429,
            error_body(),
            request_id=f"rate-limit-{len(calls)}",
            headers={"Retry-After": "120"},
        )

    client = client_factory(handler)
    with pytest.raises(RateLimitError) as caught:
        await client.request(RequestSpec("GET", "/calls"))

    assert len(calls) == 3
    assert delays == [60.0, 60.0]
    assert caught.value.request_id == "rate-limit-3"
    assert caught.value.retry_after == 120.0


async def test_500_retries_use_full_jitter_and_preserve_idempotency_key(
    client_factory, monkeypatch
):
    calls = []
    delays = []

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(client_module, "async_sleep", record_sleep)
    headers = {"Idempotency-Key": "order-A-1001"}
    spec = RequestSpec("POST", "/calls", body={"call": "unchanged"}, headers=headers)

    def handler(request):
        calls.append(request)
        return json_response(
            500,
            error_body(),
            request_id=f"server-error-{len(calls)}",
        )

    client = client_factory(handler)
    with pytest.raises(ServerError) as caught:
        await client.request(spec)

    assert len(calls) == 3
    assert delays == [0.25, 0.5]
    assert [request.headers["Idempotency-Key"] for request in calls] == [
        "order-A-1001",
        "order-A-1001",
        "order-A-1001",
    ]
    assert spec.headers is headers
    assert spec.headers == {"Idempotency-Key": "order-A-1001"}
    assert spec.body == {"call": "unchanged"}
    assert caught.value.request_id == "server-error-3"
    assert RESPONSE_SECRET not in str(caught.value)


@pytest.mark.parametrize(
    ("transport_error_type", "sdk_error_type"),
    [
        (httpx.ConnectError, APIConnectionError),
        (httpx.ReadTimeout, APITimeoutError),
    ],
)
async def test_network_and_timeout_errors_retry_and_preserve_final_cause(
    client_factory,
    monkeypatch,
    transport_error_type,
    sdk_error_type,
):
    calls = []
    failures = []
    delays = []

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(client_module, "async_sleep", record_sleep)

    def handler(request):
        calls.append(request)
        failure = transport_error_type("socket-password-secret")
        failures.append(failure)
        raise failure

    client = client_factory(handler)
    with pytest.raises(sdk_error_type) as caught:
        await client.request(RequestSpec("POST", "/calls"))

    assert len(calls) == 3
    assert delays == [0.25, 0.5]
    assert caught.value.__cause__ is failures[-1]
    assert "socket-password-secret" not in str(caught.value)
    assert "socket-password-secret" not in repr(caught.value)


async def test_retryable_false_does_not_retry_connection_error(client_factory):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("offline")

    client = client_factory(handler)
    with pytest.raises(APIConnectionError):
        await client.request(RequestSpec("GET", "/calls", retryable=False))

    assert len(calls) == 1


async def test_retry_can_return_later_success(client_factory, monkeypatch):
    calls = []

    async def record_sleep(delay):
        pass

    monkeypatch.setattr(client_module, "async_sleep", record_sleep)

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return json_response(500, error_body())
        return json_response(201, {"id": "call-1"})

    client = client_factory(handler)
    response = await client.request(RequestSpec("POST", "/calls", body={}))

    assert response.status == 201
    assert response.data == {"id": "call-1"}
    assert len(calls) == 2


async def test_redirect_is_not_followed(client_factory):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/calls"})

    client = client_factory(handler)
    response = await client.request(RequestSpec("GET", "/calls"))

    assert response.status == 302
    assert response.data is None
    assert len(calls) == 1


async def test_per_attempt_timeout_override_reaches_transport(client_factory):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, {"ok": True})

    client = client_factory(handler)
    await client.request(RequestSpec("GET", "/calls"), timeout=12.5)

    assert seen[0].extensions["timeout"] == {
        "connect": 12.5,
        "read": 12.5,
        "write": 12.5,
        "pool": 12.5,
    }


async def test_cancellation_before_io_propagates_without_transport_call(client_factory):
    calls = []

    def handler(request):
        calls.append(request)
        return json_response(200)

    client = client_factory(handler)
    task = asyncio.create_task(client.request(RequestSpec("GET", "/calls")))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls == []


async def test_cancellation_during_backoff_propagates_unchanged(client_factory, monkeypatch):
    calls = []
    cancelled = asyncio.CancelledError()

    async def cancel_sleep(delay):
        raise cancelled

    monkeypatch.setattr(client_module, "async_sleep", cancel_sleep)

    def handler(request):
        calls.append(request)
        return json_response(500, error_body())

    client = client_factory(handler)
    with pytest.raises(asyncio.CancelledError) as caught:
        await client.request(RequestSpec("GET", "/calls"))

    assert caught.value is cancelled
    assert len(calls) == 1


async def test_cancellation_during_io_is_not_converted_to_connection_error(client_factory):
    cancelled = asyncio.CancelledError()

    def handler(request):
        raise cancelled

    client = client_factory(handler)
    with pytest.raises(asyncio.CancelledError) as caught:
        await client.request(RequestSpec("GET", "/calls"))

    assert caught.value is cancelled


async def test_closed_client_fails_before_io_and_close_is_idempotent(client_factory):
    calls = []

    def handler(request):
        calls.append(request)
        return json_response(200)

    client = client_factory(handler)
    await client.aclose()
    await client.aclose()

    with pytest.raises(RuntimeError, match="closed"):
        await client.request(RequestSpec("GET", "/calls"))

    assert calls == []


@pytest.mark.parametrize(
    ("timeout", "error_type"),
    [
        (0, ValueError),
        (-1, ValueError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (True, TypeError),
    ],
)
async def test_request_rejects_invalid_timeout_before_io(client_factory, timeout, error_type):
    calls = []
    client = client_factory(lambda request: calls.append(request))

    with pytest.raises(error_type, match="timeout"):
        await client.request(RequestSpec("GET", "/calls"), timeout=timeout)

    assert calls == []


@pytest.mark.parametrize(
    ("max_retries", "error_type"),
    [(-1, ValueError), (1.5, TypeError), ("2", TypeError), (True, TypeError)],
)
async def test_request_rejects_invalid_retry_count_before_io(
    client_factory, max_retries, error_type
):
    calls = []
    client = client_factory(lambda request: calls.append(request))

    with pytest.raises(error_type, match="max_retries"):
        await client.request(RequestSpec("GET", "/calls"), max_retries=max_retries)

    assert calls == []
