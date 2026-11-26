import time

import pytest

import yolla_voice
from yolla_voice import YollaVoice
from yolla_voice.webhooks import (
    UnknownWebhookEvent,
    WebhookDispatcher,
    WebhookResponse,
    sign_webhook,
)

SECRET = "whsec_dispatch_test"
BODY = b'{"id":"evt_test","type":"webhook.test","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{}}'
UNKNOWN_BODY = b'{"id":"evt_unknown","type":"call.future","seq":1,"createdAt":"2026-11-23T10:15:00.000Z","data":{"future":true}}'
RECEIVED = b'{"received":true}'
VERIFICATION_FAILED = b'{"error":"webhook_verification_failed"}'
CALLBACK_FAILED = b'{"error":"webhook_callback_failed"}'


def signed_request(body=BODY, secret=SECRET):
    signed = sign_webhook(
        body,
        secret=secret,
        timestamp=int(time.time()),
        delivery_id="dlv_dispatch",
    )
    return signed.body, signed.headers


def assert_response(response, status, body):
    assert isinstance(response, WebhookResponse)
    assert response.status == status
    assert response.headers["Content-Type"] == "application/json"
    assert response.body == body
    assert isinstance(response.body, bytes)


def test_known_event_dispatches_to_on_and_returns_received_response():
    seen = []
    dispatcher = WebhookDispatcher(secret=SECRET, on=seen.append)

    response = dispatcher.handle(*signed_request())

    assert [event.id for event in seen] == ["evt_test"]
    assert seen[0].type == "webhook.test"
    assert_response(response, 200, RECEIVED)


def test_unknown_event_dispatches_only_to_on_unhandled():
    known = []
    unknown = []
    dispatcher = WebhookDispatcher(
        secret=SECRET,
        on=known.append,
        on_unhandled=unknown.append,
    )

    response = dispatcher.handle(*signed_request(UNKNOWN_BODY))

    assert known == []
    assert len(unknown) == 1
    assert isinstance(unknown[0], UnknownWebhookEvent)
    assert unknown[0].data == {"future": True}
    assert_response(response, 200, RECEIVED)


@pytest.mark.parametrize("body", [BODY, UNKNOWN_BODY])
def test_event_without_a_callback_is_intentionally_unhandled(body):
    dispatcher = WebhookDispatcher(secret=SECRET)

    response = dispatcher.handle(*signed_request(body))

    assert_response(response, 200, RECEIVED)


def test_verification_failure_returns_401_without_calling_callbacks():
    seen = []
    errors = []
    dispatcher = WebhookDispatcher(
        secret=SECRET,
        on=seen.append,
        on_unhandled=seen.append,
        on_error=errors.append,
    )
    body, headers = signed_request()

    response = dispatcher.handle(body, {**headers, "X-Voice-Signature": f"v1={'0' * 64}"})

    assert seen == []
    assert errors == []
    assert_response(response, 401, VERIFICATION_FAILED)
    assert SECRET.encode() not in response.body
    assert b"signature" not in response.body


def test_callback_exception_is_delivered_to_on_error_without_leaking_details():
    failure = RuntimeError("private callback detail")
    errors = []

    def callback(event):
        raise failure

    dispatcher = WebhookDispatcher(secret=SECRET, on=callback, on_error=errors.append)

    response = dispatcher.handle(*signed_request())

    assert errors == [failure]
    assert_response(response, 500, CALLBACK_FAILED)
    assert b"private callback detail" not in response.body


def test_on_error_exception_does_not_change_callback_failure_response():
    def callback(event):
        raise RuntimeError("original private detail")

    def broken_on_error(error):
        raise RuntimeError("error handler private detail")

    dispatcher = WebhookDispatcher(secret=SECRET, on=callback, on_error=broken_on_error)

    response = dispatcher.handle(*signed_request())

    assert_response(response, 500, CALLBACK_FAILED)
    assert b"original private detail" not in response.body
    assert b"error handler private detail" not in response.body


@pytest.mark.parametrize("name", ["on", "on_unhandled", "on_error"])
def test_sync_dispatcher_rejects_coroutine_callbacks_at_creation(name):
    async def callback(value):
        return None

    with pytest.raises(TypeError, match="coroutine"):
        WebhookDispatcher(secret=SECRET, **{name: callback})


def test_sync_callback_returning_awaitable_closes_it_and_reports_type_error():
    awaitables = []
    errors = []

    async def asynchronous_result():
        return None

    def callback(event):
        awaitable = asynchronous_result()
        awaitables.append(awaitable)
        return awaitable

    dispatcher = WebhookDispatcher(secret=SECRET, on=callback, on_error=errors.append)

    response = dispatcher.handle(*signed_request())

    assert len(awaitables) == 1
    assert awaitables[0].cr_frame is None
    assert len(errors) == 1
    assert isinstance(errors[0], TypeError)
    assert_response(response, 500, CALLBACK_FAILED)


def test_on_error_returning_awaitable_is_closed_without_changing_response():
    awaitables = []

    def callback(event):
        raise RuntimeError("private detail")

    async def report():
        return None

    def on_error(error):
        awaitable = report()
        awaitables.append(awaitable)
        return awaitable

    dispatcher = WebhookDispatcher(secret=SECRET, on=callback, on_error=on_error)

    response = dispatcher.handle(*signed_request())

    assert awaitables[0].cr_frame is None
    assert_response(response, 500, CALLBACK_FAILED)


def test_client_factory_binds_secret_and_per_factory_override():
    seen = []
    with YollaVoice(
        api_key="key",
        base_url="https://api.example.com",
        webhook_secret="wrong-secret",
    ) as client:
        dispatcher = client.webhooks.create_dispatcher(secret=SECRET, on=seen.append)
        response = dispatcher.handle(*signed_request())

    assert [event.id for event in seen] == ["evt_test"]
    assert_response(response, 200, RECEIVED)


def test_root_exports_dispatchers_and_response():
    assert yolla_voice.WebhookDispatcher is WebhookDispatcher
    assert yolla_voice.WebhookResponse is WebhookResponse
    assert yolla_voice.AsyncWebhookDispatcher is not None
