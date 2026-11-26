import time

from yolla_voice import AsyncYollaVoice
from yolla_voice.webhooks import (
    AsyncWebhookDispatcher,
    UnknownWebhookEvent,
    WebhookResponse,
    sign_webhook,
)

SECRET = "whsec_async_dispatch_test"
BODY = b'{"id":"evt_test","type":"webhook.test","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{}}'
UNKNOWN_BODY = b'{"id":"evt_unknown","type":"call.future","seq":1,"createdAt":"2026-11-23T10:15:00.000Z","data":{"future":true}}'
RECEIVED = b'{"received":true}'
VERIFICATION_FAILED = b'{"error":"invalid signature"}'
CALLBACK_FAILED = b'{"error":"handler failed"}'


def signed_request(body=BODY, secret=SECRET):
    signed = sign_webhook(
        body,
        secret=secret,
        timestamp=int(time.time()),
        delivery_id="dlv_async_dispatch",
    )
    return signed.body, signed.headers


def assert_response(response, status, body):
    assert isinstance(response, WebhookResponse)
    assert response.status == status
    assert response.headers["Content-Type"] == "application/json"
    assert response.body == body
    assert isinstance(response.body, bytes)


async def test_async_known_event_callback_is_awaited():
    seen = []

    async def callback(event):
        seen.append(event)

    dispatcher = AsyncWebhookDispatcher(secret=SECRET, on=callback)

    response = await dispatcher.handle(*signed_request())

    assert [event.id for event in seen] == ["evt_test"]
    assert_response(response, 200, RECEIVED)


async def test_async_unknown_event_callback_is_awaited():
    known = []
    unknown = []

    async def on_unhandled(event):
        unknown.append(event)

    dispatcher = AsyncWebhookDispatcher(
        secret=SECRET,
        on=known.append,
        on_unhandled=on_unhandled,
    )

    response = await dispatcher.handle(*signed_request(UNKNOWN_BODY))

    assert known == []
    assert len(unknown) == 1
    assert isinstance(unknown[0], UnknownWebhookEvent)
    assert_response(response, 200, RECEIVED)


async def test_async_dispatcher_supports_synchronous_event_callbacks():
    known = []
    unknown = []
    dispatcher = AsyncWebhookDispatcher(
        secret=SECRET,
        on=known.append,
        on_unhandled=unknown.append,
    )

    known_response = await dispatcher.handle(*signed_request())
    unknown_response = await dispatcher.handle(*signed_request(UNKNOWN_BODY))

    assert [event.id for event in known] == ["evt_test"]
    assert [event.id for event in unknown] == ["evt_unknown"]
    assert_response(known_response, 200, RECEIVED)
    assert_response(unknown_response, 200, RECEIVED)


async def test_async_dispatch_awaits_custom_awaitable_from_sync_callback():
    seen = []

    class CallbackAwaitable:
        def __await__(self):
            seen.append("awaited")
            return iter(())

    dispatcher = AsyncWebhookDispatcher(secret=SECRET, on=lambda event: CallbackAwaitable())

    response = await dispatcher.handle(*signed_request())

    assert seen == ["awaited"]
    assert_response(response, 200, RECEIVED)


async def test_async_verification_failure_returns_401_without_calling_on_error():
    errors = []

    async def on_error(error):
        errors.append(error)

    dispatcher = AsyncWebhookDispatcher(secret=SECRET, on_error=on_error)
    body, headers = signed_request()

    response = await dispatcher.handle(body, {**headers, "X-Voice-Signature": f"v1={'0' * 64}"})

    assert errors == []
    assert_response(response, 401, VERIFICATION_FAILED)
    assert SECRET.encode() not in response.body


async def test_async_callback_exception_is_delivered_to_async_on_error():
    failure = RuntimeError("private async callback detail")
    errors = []

    async def callback(event):
        raise failure

    async def on_error(error):
        errors.append(error)

    dispatcher = AsyncWebhookDispatcher(secret=SECRET, on=callback, on_error=on_error)

    response = await dispatcher.handle(*signed_request())

    assert errors == [failure]
    assert_response(response, 500, CALLBACK_FAILED)
    assert b"private async callback detail" not in response.body


async def test_async_dispatcher_supports_synchronous_on_error():
    failure = RuntimeError("private detail")
    errors = []

    async def callback(event):
        raise failure

    dispatcher = AsyncWebhookDispatcher(secret=SECRET, on=callback, on_error=errors.append)

    response = await dispatcher.handle(*signed_request())

    assert errors == [failure]
    assert_response(response, 500, CALLBACK_FAILED)


async def test_async_on_error_exception_does_not_change_response():
    async def callback(event):
        raise RuntimeError("original private detail")

    async def broken_on_error(error):
        raise RuntimeError("error handler private detail")

    dispatcher = AsyncWebhookDispatcher(secret=SECRET, on=callback, on_error=broken_on_error)

    response = await dispatcher.handle(*signed_request())

    assert_response(response, 500, CALLBACK_FAILED)
    assert b"original private detail" not in response.body
    assert b"error handler private detail" not in response.body


async def test_async_unhandled_callback_exception_uses_same_error_boundary():
    failure = RuntimeError("unhandled private detail")
    errors = []

    async def on_unhandled(event):
        raise failure

    dispatcher = AsyncWebhookDispatcher(
        secret=SECRET,
        on_unhandled=on_unhandled,
        on_error=errors.append,
    )

    response = await dispatcher.handle(*signed_request(UNKNOWN_BODY))

    assert errors == [failure]
    assert_response(response, 500, CALLBACK_FAILED)
    assert b"unhandled private detail" not in response.body


async def test_async_client_factory_binds_secret_and_per_factory_override():
    seen = []

    async def callback(event):
        seen.append(event)

    async with AsyncYollaVoice(
        api_key="key",
        base_url="https://api.example.com",
        webhook_secret="wrong-secret",
    ) as client:
        dispatcher = client.webhooks.create_async_dispatcher(secret=SECRET, on=callback)
        response = await dispatcher.handle(*signed_request())

    assert [event.id for event in seen] == ["evt_test"]
    assert_response(response, 200, RECEIVED)
