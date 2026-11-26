import json

import httpx
import pytest

import yolla_voice
import yolla_voice._http.client as http_module
from yolla_voice import AsyncYollaVoice, YollaVoice, errors, models, pagination, webhooks
from yolla_voice.errors import ServerError


def json_response(status, body):
    return httpx.Response(
        status,
        content=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )


def balance_payload():
    return {
        "available": {"amount": "9.50", "currency": "USD"},
        "balance": {"amount": "10.00", "currency": "USD"},
        "billingMode": "prepaid",
    }


def error_response():
    return json_response(500, {"error": {"code": "temporary", "message": "Try again"}})


def test_environment_fallback_and_explicit_precedence_are_observable(monkeypatch):
    monkeypatch.setenv("YOLLA_API_KEY", "environment-api-secret")
    monkeypatch.setenv("YOLLA_BASE_URL", "https://environment.example.com/")
    monkeypatch.setenv("YOLLA_WEBHOOK_SECRET", "environment-webhook-secret")
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, balance_payload())

    environment_client = YollaVoice(transport=httpx.MockTransport(handler))
    environment_client.balance.get()
    explicit_client = YollaVoice(
        api_key="explicit-api-secret",
        base_url="https://explicit.example.com/",
        webhook_secret=("explicit-webhook-one", "explicit-webhook-two"),
        transport=httpx.MockTransport(handler),
    )
    explicit_client.balance.get()

    assert str(seen[0].url) == "https://environment.example.com/v1/balance"
    assert seen[0].headers["Authorization"] == "Bearer environment-api-secret"
    assert str(seen[1].url) == "https://explicit.example.com/v1/balance"
    assert seen[1].headers["Authorization"] == "Bearer explicit-api-secret"
    for client in (environment_client, explicit_client):
        rendered = repr(client) + str(client)
        for secret in (
            "environment-api-secret",
            "environment-webhook-secret",
            "explicit-api-secret",
            "explicit-webhook-one",
            "explicit-webhook-two",
        ):
            assert secret not in rendered
    environment_client.close()
    explicit_client.close()


async def test_async_environment_fallback_and_explicit_precedence(monkeypatch):
    monkeypatch.setenv("YOLLA_API_KEY", "environment-api-secret")
    monkeypatch.setenv("YOLLA_BASE_URL", "https://environment.example.com/")
    monkeypatch.setenv("YOLLA_WEBHOOK_SECRET", "environment-webhook-secret")
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, balance_payload())

    environment_client = AsyncYollaVoice(transport=httpx.MockTransport(handler))
    await environment_client.balance.get()
    explicit_client = AsyncYollaVoice(
        api_key="explicit-api-secret",
        base_url="https://explicit.example.com/",
        webhook_secret=("explicit-webhook-one", "explicit-webhook-two"),
        transport=httpx.MockTransport(handler),
    )
    await explicit_client.balance.get()

    assert str(seen[0].url) == "https://environment.example.com/v1/balance"
    assert seen[0].headers["Authorization"] == "Bearer environment-api-secret"
    assert str(seen[1].url) == "https://explicit.example.com/v1/balance"
    assert seen[1].headers["Authorization"] == "Bearer explicit-api-secret"
    for client in (environment_client, explicit_client):
        rendered = repr(client) + str(client)
        assert "environment-api-secret" not in rendered
        assert "environment-webhook-secret" not in rendered
        assert "explicit-api-secret" not in rendered
        assert "explicit-webhook-one" not in rendered
        assert "explicit-webhook-two" not in rendered
    await environment_client.aclose()
    await explicit_client.aclose()


@pytest.mark.parametrize("client_type", [YollaVoice, AsyncYollaVoice])
def test_missing_api_key_names_option_and_environment(client_type, monkeypatch):
    monkeypatch.delenv("YOLLA_API_KEY", raising=False)
    monkeypatch.delenv("YOLLA_BASE_URL", raising=False)

    with pytest.raises(ValueError) as caught:
        client_type(base_url="https://api.example.com")

    assert "api_key" in str(caught.value)
    assert "YOLLA_API_KEY" in str(caught.value)


@pytest.mark.parametrize("client_type", [YollaVoice, AsyncYollaVoice])
def test_missing_base_url_does_not_leak_api_key(client_type, monkeypatch):
    monkeypatch.delenv("YOLLA_BASE_URL", raising=False)

    with pytest.raises(ValueError) as caught:
        client_type(api_key="must-not-leak")

    assert "base_url" in str(caught.value)
    assert "YOLLA_BASE_URL" in str(caught.value)
    assert "must-not-leak" not in str(caught.value)


def test_sync_defaults_are_30_seconds_and_two_retries(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return error_response()

    monkeypatch.setattr(http_module, "sleep", lambda delay: None)
    client = YollaVoice(
        api_key="key", base_url="https://api.example.com", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ServerError):
        client.balance.get()

    assert len(seen) == 3
    assert all(request.extensions["timeout"]["read"] == 30.0 for request in seen)
    client.close()


async def test_async_defaults_are_30_seconds_and_two_retries(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return error_response()

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(http_module, "async_sleep", no_sleep)
    client = AsyncYollaVoice(
        api_key="key", base_url="https://api.example.com", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ServerError):
        await client.balance.get()

    assert len(seen) == 3
    assert all(request.extensions["timeout"]["read"] == 30.0 for request in seen)
    await client.aclose()


def test_sync_per_call_overrides_replace_defaults(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return error_response()

    monkeypatch.setattr(http_module, "sleep", lambda delay: None)
    client = YollaVoice(
        api_key="key",
        base_url="https://api.example.com",
        timeout=20,
        max_retries=5,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ServerError):
        client.balance.get(timeout=7.5, max_retries=0)

    assert len(seen) == 1
    assert seen[0].extensions["timeout"]["read"] == 7.5
    client.close()


async def test_async_per_call_overrides_replace_defaults(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return error_response()

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(http_module, "async_sleep", no_sleep)
    client = AsyncYollaVoice(
        api_key="key",
        base_url="https://api.example.com",
        timeout=20,
        max_retries=5,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ServerError):
        await client.balance.get(timeout=7.5, max_retries=0)

    assert len(seen) == 1
    assert seen[0].extensions["timeout"]["read"] == 7.5
    await client.aclose()


def test_sync_context_manager_close_and_closed_zero_io():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, balance_payload())

    client = YollaVoice(
        api_key="closed-secret",
        base_url="https://api.example.com",
        webhook_secret="closed-webhook-secret",
        transport=httpx.MockTransport(handler),
    )
    with client as entered:
        assert entered is client
        entered.balance.get()
    client.close()

    with pytest.raises(RuntimeError, match="closed") as caught:
        client.calls.get("call-1")
    assert len(seen) == 1
    assert "closed-secret" not in str(caught.value)
    assert "closed-webhook-secret" not in str(caught.value)


async def test_async_context_manager_close_and_closed_zero_io():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(200, balance_payload())

    client = AsyncYollaVoice(
        api_key="closed-secret",
        base_url="https://api.example.com",
        webhook_secret="closed-webhook-secret",
        transport=httpx.MockTransport(handler),
    )
    async with client as entered:
        assert entered is client
        await entered.balance.get()
    await client.aclose()

    with pytest.raises(RuntimeError, match="closed") as caught:
        await client.calls.get("call-1")
    assert len(seen) == 1
    assert "closed-secret" not in str(caught.value)
    assert "closed-webhook-secret" not in str(caught.value)


def test_root_exports_public_clients_models_errors_and_pagination():
    expected = (
        set(models.__all__)
        | set(errors.__all__)
        | set(pagination.__all__)
        | set(webhooks.__all__)
        | {"AsyncYollaVoice", "YollaVoice", "CreateCallResult", "__version__", "webhooks"}
    )

    assert set(yolla_voice.__all__) == expected
    for name in expected:
        assert getattr(yolla_voice, name) is not None
