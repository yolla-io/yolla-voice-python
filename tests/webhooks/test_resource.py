from typing import Any

import pytest

import yolla_voice
from yolla_voice import AsyncYollaVoice, Webhooks, YollaVoice
from yolla_voice.webhooks import SignedWebhook, UnknownWebhookEvent

TIMESTAMP = 1700000000
SECRET = "whsec_test"
BODY = b'{"id":"evt_test","type":"webhook.test","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{}}'
SIGNATURE = "v1=7b6fdffeec4f9fb2759d6bcbd22d8c35a73435790b58617d5041b0f1df059a19"
CLIENT_OPTIONS: dict[str, Any] = {"api_key": "key"}


def assert_bound_webhooks(client):
    assert isinstance(client.webhooks, Webhooks)
    signed = client.webhooks.sign(BODY, timestamp=TIMESTAMP, delivery_id="dlv_deterministic")
    event = client.webhooks.verify(signed.body, signed.headers, now=TIMESTAMP)
    overridden = client.webhooks.sign(
        BODY,
        secret="override-secret",
        timestamp=TIMESTAMP,
        delivery_id="dlv_override",
    )

    assert isinstance(signed, SignedWebhook)
    assert signed.headers["X-Voice-Signature"] == SIGNATURE
    assert event.id == "evt_test"
    assert overridden.headers["X-Voice-Signature"] != SIGNATURE
    rendered = repr(client.webhooks) + str(client.webhooks)
    assert SECRET not in rendered
    assert SIGNATURE not in rendered
    assert SIGNATURE[3:] not in rendered


def test_sync_client_binds_secret_and_per_call_secret_overrides():
    with YollaVoice(**CLIENT_OPTIONS, webhook_secret=SECRET) as client:
        assert_bound_webhooks(client)


async def test_async_client_binds_same_webhook_facade():
    async with AsyncYollaVoice(**CLIENT_OPTIONS, webhook_secret=SECRET) as client:
        assert_bound_webhooks(client)


@pytest.mark.parametrize("client_type", [YollaVoice, AsyncYollaVoice])
async def test_client_without_secret_uses_environment(client_type, monkeypatch):
    monkeypatch.setenv("YOLLA_WEBHOOK_SECRET", SECRET)

    client = client_type(**CLIENT_OPTIONS)
    signed = client.webhooks.sign(BODY, timestamp=TIMESTAMP, delivery_id="dlv_deterministic")

    assert signed.headers["X-Voice-Signature"] == SIGNATURE
    if isinstance(client, AsyncYollaVoice):
        await client.aclose()
    else:
        client.close()


@pytest.mark.parametrize("client_type", [YollaVoice, AsyncYollaVoice])
async def test_client_without_any_secret_fails_safely_at_operation(client_type, monkeypatch):
    monkeypatch.delenv("YOLLA_WEBHOOK_SECRET", raising=False)
    client = client_type(**CLIENT_OPTIONS)

    with pytest.raises(ValueError) as caught:
        client.webhooks.sign(BODY)

    assert "YOLLA_WEBHOOK_SECRET" in str(caught.value)
    assert SECRET not in str(caught.value)
    if isinstance(client, AsyncYollaVoice):
        await client.aclose()
    else:
        client.close()


def test_root_exports_public_webhook_helpers_and_types():
    expected = {
        "KnownWebhookEvent",
        "SignedWebhook",
        "UnknownWebhookEvent",
        "WebhookEvent",
        "WebhookSecret",
        "Webhooks",
        "parse_event",
        "sign_webhook",
        "verify_webhook",
    }

    assert expected <= set(yolla_voice.__all__)
    assert yolla_voice.UnknownWebhookEvent is UnknownWebhookEvent
    for name in expected:
        assert getattr(yolla_voice, name) is not None
