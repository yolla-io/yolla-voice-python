import time

import yolla_voice
from yolla_voice.webhooks import AsyncWebhookDispatcher, create_asgi_app, sign_webhook

MAX_BODY_BYTES = 1_048_576
SECRET = "whsec_asgi_test"
BODY = b'{"id":"evt_test","type":"webhook.test","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{}}'
RECEIVED = b'{"received":true}'
VERIFICATION_FAILED = b'{"error":"invalid signature"}'
CALLBACK_FAILED = b'{"error":"handler failed"}'
METHOD_NOT_ALLOWED = b'{"error":"method not allowed"}'
PAYLOAD_TOO_LARGE = b'{"error":"payload too large"}'


def signed_request(body=BODY):
    signed = sign_webhook(
        body,
        secret=SECRET,
        timestamp=int(time.time()),
        delivery_id="dlv_asgi",
    )
    return signed.body, signed.headers


def sized_body(size):
    prefix = b'{"id":"evt_test","type":"call.future","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{"padding":"'
    suffix = b'"}}'
    return prefix + b"x" * (size - len(prefix) - len(suffix)) + suffix


async def request(
    app,
    *,
    method="POST",
    body=BODY,
    headers=None,
    chunks=None,
    content_length=True,
    final_more_body=False,
):
    raw_headers = [
        (name.lower().encode("ascii"), value.encode("ascii"))
        for name, value in (headers or {}).items()
    ]
    if content_length:
        raw_headers.append((b"content-length", str(len(body)).encode("ascii")))
    messages = chunks if chunks is not None else [body]
    requests = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(messages) - 1 or final_more_body,
        }
        for index, chunk in enumerate(messages)
    ]
    receive_calls = 0

    async def receive():
        nonlocal receive_calls
        if receive_calls == len(requests):
            raise AssertionError("ASGI application attempted an unbounded read")
        message = requests[receive_calls]
        receive_calls += 1
        return message

    sent = []

    async def send(message):
        sent.append(message)

    await app({"type": "http", "method": method, "headers": raw_headers}, receive, send)
    assert len(sent) == 2
    start, end = sent
    response_headers = {
        name.decode("ascii"): value.decode("ascii") for name, value in start["headers"]
    }
    return start["status"], response_headers, end, receive_calls


def assert_response(result, status, body, *, allow=False):
    actual_status, headers, end, _ = result
    expected_headers = {
        "content-type": "application/json",
        "content-length": str(len(body)),
    }
    if allow:
        expected_headers["allow"] = "POST"
    assert actual_status == status
    assert headers == expected_headers
    assert end == {"type": "http.response.body", "body": body, "more_body": False}


async def test_valid_lowercase_headers_return_exact_200_response():
    body, headers = signed_request()
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))

    result = await request(app, body=body, headers=headers)

    assert_response(result, 200, RECEIVED)


async def test_invalid_signature_returns_exact_401_response():
    body, headers = signed_request()
    headers["X-Voice-Signature"] = f"v1={'0' * 64}"
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))

    result = await request(app, body=body, headers=headers)

    assert_response(result, 401, VERIFICATION_FAILED)


async def test_callback_failure_returns_exact_500_without_internal_details():
    async def callback(event):
        raise RuntimeError("private ASGI callback detail")

    body, headers = signed_request()
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET, on={"webhook.test": callback}))

    result = await request(app, body=body, headers=headers)

    assert_response(result, 500, CALLBACK_FAILED)
    assert b"private ASGI callback detail" not in result[2]["body"]


async def test_non_post_returns_405_allow_post_without_reading_body():
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))

    result = await request(app, method="GET", content_length=False)

    assert_response(result, 405, METHOD_NOT_ALLOWED, allow=True)
    assert result[3] == 0


async def test_content_length_over_limit_returns_413_without_reading_body():
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))
    body, headers = signed_request()
    headers["content-length"] = str(MAX_BODY_BYTES + 1)

    result = await request(app, body=body, headers=headers, content_length=False)

    assert_response(result, 413, PAYLOAD_TOO_LARGE)
    assert result[3] == 0


async def test_exactly_one_mib_stream_is_accepted():
    body, headers = signed_request(sized_body(MAX_BODY_BYTES))
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))

    result = await request(
        app,
        body=body,
        headers=headers,
        chunks=[body[:17], body[17:]],
        content_length=False,
    )

    assert_response(result, 200, RECEIVED)


async def test_one_byte_over_one_mib_stream_is_rejected_without_another_receive():
    body, headers = signed_request(sized_body(MAX_BODY_BYTES + 1))
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))

    result = await request(
        app,
        body=body,
        headers=headers,
        chunks=[body[:100], body[100:]],
        content_length=False,
        final_more_body=True,
    )

    assert_response(result, 413, PAYLOAD_TOO_LARGE)
    assert result[3] == 2


async def test_custom_limit_stops_at_limit_plus_one_across_chunk_boundaries():
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET), max_body_bytes=8)

    result = await request(
        app,
        chunks=[b"123", b"456", b"789", b"unread"],
        content_length=False,
        final_more_body=True,
    )

    assert_response(result, 413, PAYLOAD_TOO_LARGE)
    assert result[3] == 3


def test_asgi_factory_is_exported_from_both_public_modules():
    assert yolla_voice.create_asgi_app is create_asgi_app


def scripted_receive(messages):
    queue = list(messages)

    async def receive():
        if not queue:
            raise AssertionError("ASGI application read past the scripted messages")
        return queue.pop(0)

    return receive


async def test_client_disconnect_mid_body_sends_nothing_and_skips_dispatch():
    handled = []
    app = create_asgi_app(
        AsyncWebhookDispatcher(secret=SECRET, on={"webhook.test": handled.append}),
    )
    body, headers = signed_request()
    sent = []

    async def send(message):
        sent.append(message)

    receive = scripted_receive(
        [
            {"type": "http.request", "body": body[:10], "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    raw_headers = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    await app({"type": "http", "method": "POST", "headers": raw_headers}, receive, send)

    assert sent == []
    assert handled == []


async def test_lifespan_scope_completes_startup_and_shutdown():
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))
    sent = []

    async def send(message):
        sent.append(message)

    receive = scripted_receive([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    await app({"type": "lifespan"}, receive, send)

    assert sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


async def test_websocket_scope_is_closed_with_policy_violation():
    app = create_asgi_app(AsyncWebhookDispatcher(secret=SECRET))
    sent = []

    async def send(message):
        sent.append(message)

    await app({"type": "websocket", "headers": []}, scripted_receive([]), send)

    assert sent == [{"type": "websocket.close", "code": 1008}]
