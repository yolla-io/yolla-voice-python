import io
import socket
import threading
import time
from wsgiref.simple_server import WSGIRequestHandler, make_server

import yolla_voice
from yolla_voice.webhooks import WebhookDispatcher, create_wsgi_app, sign_webhook

MAX_BODY_BYTES = 1_048_576
SECRET = "whsec_wsgi_test"
BODY = b'{"id":"evt_test","type":"webhook.test","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{}}'
RECEIVED = b'{"received":true}'
VERIFICATION_FAILED = b'{"error":"webhook_verification_failed"}'
CALLBACK_FAILED = b'{"error":"webhook_callback_failed"}'
METHOD_NOT_ALLOWED = b'{"error":"method_not_allowed"}'
PAYLOAD_TOO_LARGE = b'{"error":"payload_too_large"}'
LENGTH_REQUIRED = b'{"error":"length_required"}'
_DEFAULT_CONTENT_LENGTH = object()


class BoundedInput:
    def __init__(self, body, chunk_size):
        self._stream = io.BytesIO(body)
        self._chunk_size = chunk_size
        self.requested_sizes = []
        self.bytes_read = 0

    def read(self, size=-1):
        if size < 0:
            raise AssertionError("WSGI application attempted an unbounded read")
        self.requested_sizes.append(size)
        chunk = self._stream.read(min(size, self._chunk_size))
        self.bytes_read += len(chunk)
        return chunk


def signed_request(body=BODY):
    signed = sign_webhook(
        body,
        secret=SECRET,
        timestamp=int(time.time()),
        delivery_id="dlv_wsgi",
    )
    return signed.body, signed.headers


def sized_body(size):
    prefix = b'{"id":"evt_test","type":"call.future","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{"padding":"'
    suffix = b'"}}'
    return prefix + b"x" * (size - len(prefix) - len(suffix)) + suffix


def request(
    app,
    *,
    method="POST",
    body=BODY,
    headers=None,
    stream=None,
    content_length=_DEFAULT_CONTENT_LENGTH,
    terminated=False,
):
    input_stream = stream if stream is not None else io.BytesIO(body)
    environ = {"REQUEST_METHOD": method, "wsgi.input": input_stream}
    if terminated:
        environ["wsgi.input_terminated"] = True
    if content_length is _DEFAULT_CONTENT_LENGTH:
        content_length = str(len(body))
    if content_length is not None:
        environ["CONTENT_LENGTH"] = content_length
    for name, value in (headers or {}).items():
        environ[f"HTTP_{name.upper().replace('-', '_')}"] = value
    started = []

    def start_response(status, response_headers):
        started.append((status, response_headers))

    response_body = b"".join(app(environ, start_response))
    assert len(started) == 1
    status, response_headers = started[0]
    return status, response_headers, response_body, input_stream


def assert_response(result, status, body, *, allow=False):
    actual_status, headers, actual_body, _ = result
    expected_headers = [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
    ]
    if allow:
        expected_headers.append(("Allow", "POST"))
    assert actual_status == status
    assert headers == expected_headers
    assert actual_body == body


def test_valid_headers_return_exact_200_response():
    body, headers = signed_request()
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))

    result = request(app, body=body, headers=headers)

    assert_response(result, "200 OK", RECEIVED)


def test_invalid_signature_returns_exact_401_response():
    body, headers = signed_request()
    headers["X-Voice-Signature"] = f"v1={'0' * 64}"
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))

    result = request(app, body=body, headers=headers)

    assert_response(result, "401 Unauthorized", VERIFICATION_FAILED)
    assert b"signature" not in result[2]


def test_callback_failure_returns_exact_500_without_internal_details():
    def callback(event):
        raise RuntimeError("private WSGI callback detail")

    body, headers = signed_request()
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET, on=callback))

    result = request(app, body=body, headers=headers)

    assert_response(result, "500 Internal Server Error", CALLBACK_FAILED)
    assert b"private WSGI callback detail" not in result[2]


def test_non_post_returns_405_allow_post_without_reading_body():
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))
    stream = BoundedInput(BODY, chunk_size=10)

    result = request(app, method="GET", stream=stream, content_length=None)

    assert_response(result, "405 Method Not Allowed", METHOD_NOT_ALLOWED, allow=True)
    assert stream.requested_sizes == []


def test_content_length_over_limit_returns_413_without_reading_body():
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))
    body, headers = signed_request()
    stream = BoundedInput(body, chunk_size=10)

    result = request(
        app,
        body=body,
        headers=headers,
        stream=stream,
        content_length=str(MAX_BODY_BYTES + 1),
    )

    assert_response(result, "413 Payload Too Large", PAYLOAD_TOO_LARGE)
    assert stream.requested_sizes == []


def test_exactly_one_mib_stream_is_accepted():
    body, headers = signed_request(sized_body(MAX_BODY_BYTES))
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))

    result = request(app, body=body, headers=headers, content_length=None, terminated=True)

    assert_response(result, "200 OK", RECEIVED)


def test_one_byte_over_one_mib_stream_is_rejected():
    body, headers = signed_request(sized_body(MAX_BODY_BYTES + 1))
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))

    result = request(app, body=body, headers=headers, content_length=None, terminated=True)

    assert_response(result, "413 Payload Too Large", PAYLOAD_TOO_LARGE)


def test_partial_reads_are_bounded_and_stop_at_limit_plus_one():
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET), max_body_bytes=8)
    stream = BoundedInput(b"123456789 unread", chunk_size=3)

    result = request(app, stream=stream, content_length=None, terminated=True)

    assert_response(result, "413 Payload Too Large", PAYLOAD_TOO_LARGE)
    assert stream.bytes_read == 9
    assert stream.requested_sizes == [9, 6, 3]


def test_missing_content_length_without_terminated_input_returns_411_without_reading():
    body, headers = signed_request()
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))
    stream = BoundedInput(body, chunk_size=10)

    result = request(app, body=body, headers=headers, stream=stream, content_length=None)

    assert_response(result, "411 Length Required", LENGTH_REQUIRED)
    assert stream.requested_sizes == []


def test_reads_exactly_content_length_and_never_past_it():
    body, headers = signed_request()
    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))
    stream = BoundedInput(body + b"next pipelined request", chunk_size=7)

    result = request(app, body=body, headers=headers, stream=stream)

    assert_response(result, "200 OK", RECEIVED)
    assert stream.bytes_read == len(body)
    assert max(stream.requested_sizes) <= len(body)


def test_keep_alive_request_on_wsgiref_server_gets_a_response():
    body, headers = signed_request()

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, format, *args):
            pass

    app = create_wsgi_app(WebhookDispatcher(secret=SECRET))
    server = make_server("127.0.0.1", 0, app, handler_class=QuietHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        with socket.create_connection(server.server_address, timeout=5) as connection:
            header_lines = "".join(f"{name}: {value}\r\n" for name, value in headers.items())
            connection.sendall(
                (
                    "POST / HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n"
                    f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                    f"{header_lines}\r\n"
                ).encode("ascii")
                + body
            )
            status_line = connection.recv(64).split(b"\r\n", 1)[0]
    finally:
        thread.join(timeout=5)
        server.server_close()

    assert status_line.endswith(b"200 OK")


def test_wsgi_factory_is_exported_from_both_public_modules():
    assert yolla_voice.create_wsgi_app is create_wsgi_app
