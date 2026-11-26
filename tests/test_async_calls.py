import json
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest

import yolla_voice._http.client as http_module
import yolla_voice.resources.calls as calls_module
from yolla_voice import AsyncYollaVoice, Call, CallStatus, CreateCallRequest, CreateCallResponse
from yolla_voice.errors import YollaVoiceError

API_KEY = "test-api-key"
BASE_URL = "https://api.example.com"


def call_payload(call_id="call-1"):
    return {
        "id": call_id,
        "status": "created",
        "to": "14155550100",
        "from": "14155550199",
        "externalUserId": "user-1",
        "createdAt": "2026-11-25T12:00:00Z",
        "expiresAt": "2026-11-25T13:00:00Z",
    }


def create_payload():
    return {
        "id": "call-1",
        "status": "created",
        "callToken": "token-1",
        "to": "14155550100",
        "from": "14155550199",
        "createdAt": "2026-11-25T12:00:00Z",
        "expiresAt": "2026-11-25T13:00:00Z",
        "maxDuration": 14400,
    }


def json_response(status, body=None, *, request_id=None):
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if request_id is not None:
        headers["X-Request-Id"] = request_id
    content = b"" if body is None else json.dumps(body).encode()
    return httpx.Response(status, content=content, headers=headers)


@pytest.fixture
async def client_factory():
    clients = []

    def factory(handler, **options):
        client = AsyncYollaVoice(
            api_key=API_KEY,
            base_url=BASE_URL,
            transport=httpx.MockTransport(handler),
            **options,
        )
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


@pytest.mark.parametrize(("status", "replayed"), [(200, True), (201, False)])
async def test_create_uses_aliases_idempotency_and_status_replay(client_factory, status, replayed):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(status, create_payload())

    client = client_factory(handler)
    result = await client.calls.create(
        CreateCallRequest(to="14155550100", from_="14155550199", external_user_id="user-1"),
        idempotency_key="k" * 128,
        timeout=4.5,
        max_retries=0,
    )

    assert isinstance(result.call, CreateCallResponse)
    assert result.call.id == "call-1"
    assert result.replayed is replayed
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/v1/calls"
    assert request.headers["Idempotency-Key"] == "k" * 128
    assert json.loads(request.content) == {
        "to": "14155550100",
        "from": "14155550199",
        "externalUserId": "user-1",
    }
    assert request.extensions["timeout"]["read"] == 4.5


async def test_create_generates_one_uuid_and_reuses_it_on_retries(client_factory, monkeypatch):
    seen_keys = []

    def handler(request):
        seen_keys.append(request.headers["Idempotency-Key"])
        if len(seen_keys) == 1:
            return json_response(500, {"error": {"code": "temporary", "message": "Try again"}})
        return json_response(201, create_payload())

    generated = UUID("12345678-1234-5678-1234-567812345678")
    uuid4 = Mock(return_value=generated)
    monkeypatch.setattr(calls_module, "uuid4", uuid4)

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(http_module, "async_sleep", no_sleep)
    client = client_factory(handler)

    result = await client.calls.create(
        CreateCallRequest(to="14155550100", external_user_id="user-1")
    )

    assert result.replayed is False
    assert seen_keys == [str(generated), str(generated)]
    uuid4.assert_called_once_with()


async def test_create_rejects_129_character_key_before_io(client_factory):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(201, create_payload())

    client = client_factory(handler)
    with pytest.raises(ValueError, match="128"):
        await client.calls.create(
            CreateCallRequest(to="14155550100", external_user_id="user-1"),
            idempotency_key="x" * 129,
        )

    assert seen == []


async def test_list_uses_wire_filters_and_datetime_values(client_factory):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, {"items": [call_payload()], "nextCursor": None})

    client = client_factory(handler)
    page = await client.calls.list(
        status=CallStatus.completed,
        external_user_id="user 1",
        from_=datetime(2026, 11, 26, 1, 2, 3, tzinfo=UTC),
        to="2026-11-27T01:02:03Z",
        limit=25,
        cursor="a/b",
        timeout=6.0,
        max_retries=0,
    )

    assert [item.id for item in page.items] == ["call-1"]
    assert page.next_cursor is None
    assert dict(seen[0].url.params) == {
        "status": "completed",
        "externalUserId": "user 1",
        "from": "2026-11-26T01:02:03+00:00",
        "to": "2026-11-27T01:02:03Z",
        "limit": "25",
        "cursor": "a/b",
    }


@pytest.mark.parametrize(
    ("method_name", "suffix", "http_method"),
    [
        ("get", "", "GET"),
        ("end", "/end", "POST"),
        ("hold", "/hold", "POST"),
        ("unhold", "/unhold", "POST"),
    ],
)
async def test_call_methods_percent_encode_ids(client_factory, method_name, suffix, http_method):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, call_payload())

    client = client_factory(handler)
    result = await getattr(client.calls, method_name)("call /?#%", timeout=3.0, max_retries=0)

    assert isinstance(result, Call)
    assert seen[0].method == http_method
    assert str(seen[0].url) == f"{BASE_URL}/v1/calls/call%20%2F%3F%23%25{suffix}"


async def test_iter_all_is_lazy_replaces_cursor_and_preserves_overrides(
    client_factory, monkeypatch
):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.params["cursor"] == "caller-cursor":
            return json_response(200, {"items": [call_payload("call-1")], "nextCursor": "next"})
        if request.url.params["cursor"] == "next":
            return json_response(200, {"items": [call_payload("call-2")], "nextCursor": None})
        raise AssertionError("unexpected cursor")

    client = client_factory(handler)
    request_spy = Mock(wraps=client._http.request)
    monkeypatch.setattr(client._http, "request", request_spy)

    iterator = client.calls.iter_all(
        status="completed",
        external_user_id="user-1",
        from_="2026-11-25T00:00:00Z",
        to="2026-11-27T00:00:00Z",
        limit=1,
        cursor="caller-cursor",
        timeout=8.0,
        max_retries=4,
    )
    assert seen == []

    assert [call.id async for call in iterator] == ["call-1", "call-2"]
    assert [dict(request.url.params) for request in seen] == [
        {
            "status": "completed",
            "externalUserId": "user-1",
            "from": "2026-11-25T00:00:00Z",
            "to": "2026-11-27T00:00:00Z",
            "limit": "1",
            "cursor": "caller-cursor",
        },
        {
            "status": "completed",
            "externalUserId": "user-1",
            "from": "2026-11-25T00:00:00Z",
            "to": "2026-11-27T00:00:00Z",
            "limit": "1",
            "cursor": "next",
        },
    ]
    assert request_spy.call_args_list[0].kwargs == {"timeout": 8.0, "max_retries": 4}
    assert request_spy.call_args_list[1].kwargs == {"timeout": 8.0, "max_retries": 4}


@pytest.mark.parametrize("body", [None, {}])
async def test_malformed_success_becomes_invalid_response_with_metadata(client_factory, body):
    def handler(request):
        return json_response(200, body, request_id="request-invalid")

    client = client_factory(handler)
    with pytest.raises(YollaVoiceError) as caught:
        await client.calls.get("call-1")

    assert caught.value.code == "invalid_response"
    assert caught.value.status == 200
    assert caught.value.request_id == "request-invalid"


@pytest.mark.parametrize("field", ["from_", "to"])
async def test_list_rejects_naive_datetimes_before_io(client_factory, field):
    seen = []
    client = client_factory(lambda request: seen.append(request))

    with pytest.raises(ValueError, match="timezone-aware"):
        await client.calls.list(**{field: datetime(2026, 11, 25, 12, 0)})

    assert seen == []


async def test_create_serializes_extra_fields_as_json(client_factory):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return json_response(201, create_payload())

    client = client_factory(handler)
    request = CreateCallRequest.model_validate(
        {
            "to": "14155550100",
            "externalUserId": "user-1",
            "scheduledAt": datetime(2026, 11, 25, 12, 0, tzinfo=UTC),
        }
    )
    await client.calls.create(request, idempotency_key="key-1")

    assert seen[0]["scheduledAt"] == "2026-11-25T12:00:00Z"


@pytest.mark.parametrize(("action", "attempts"), [("hold", 1), ("unhold", 1), ("end", 3)])
async def test_call_actions_retry_transport_errors_only_when_repeatable(
    client_factory, monkeypatch, action, attempts
):
    seen = []

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(http_module, "async_sleep", no_sleep)

    def handler(request):
        seen.append(request)
        raise httpx.ReadTimeout("lost response")

    client = client_factory(handler)
    with pytest.raises(YollaVoiceError):
        await getattr(client.calls, action)("call-1")

    assert len(seen) == attempts


@pytest.mark.parametrize("action", ["hold", "unhold"])
async def test_hold_actions_retry_unavailable_responses(client_factory, monkeypatch, action):
    seen = []

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(http_module, "async_sleep", no_sleep)

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return json_response(503, {"error": {"code": "unavailable", "message": "Retry"}})
        return json_response(200, call_payload())

    client = client_factory(handler)
    call = await getattr(client.calls, action)("call-1")

    assert call.id == "call-1"
    assert len(seen) == 2
