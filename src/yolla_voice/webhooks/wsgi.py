from wsgiref.types import StartResponse, WSGIApplication, WSGIEnvironment

from .dispatch import WebhookDispatcher

_METHOD_NOT_ALLOWED = b'{"error":"method_not_allowed"}'
_PAYLOAD_TOO_LARGE = b'{"error":"payload_too_large"}'
_LENGTH_REQUIRED = b'{"error":"length_required"}'
_REASONS = {
    200: "OK",
    401: "Unauthorized",
    405: "Method Not Allowed",
    411: "Length Required",
    413: "Payload Too Large",
    500: "Internal Server Error",
}


def _response(
    status: int,
    body: bytes,
    *,
    allow_post: bool = False,
) -> tuple[str, list[tuple[str, str]], list[bytes]]:
    headers = [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
    ]
    if allow_post:
        headers.append(("Allow", "POST"))
    return f"{status} {_REASONS[status]}", headers, [body]


def _content_length(value: object) -> int | None:
    if not isinstance(value, str) or not value.strip().isdigit():
        return None
    return int(value)


def create_wsgi_app(
    dispatcher: WebhookDispatcher,
    *,
    max_body_bytes: int = 1_048_576,
) -> WSGIApplication:
    def app(environ: WSGIEnvironment, start_response: StartResponse) -> list[bytes]:
        if environ.get("REQUEST_METHOD") != "POST":
            status, headers, body = _response(405, _METHOD_NOT_ALLOWED, allow_post=True)
            start_response(status, headers)
            return body

        content_length = _content_length(environ.get("CONTENT_LENGTH"))
        terminated = bool(environ.get("wsgi.input_terminated"))
        if content_length is None and not terminated:
            # PEP 3333 forbids reading past CONTENT_LENGTH; without it, a read can
            # block on a keep-alive socket until the client gives up.
            status, headers, body = _response(411, _LENGTH_REQUIRED)
            start_response(status, headers)
            return body
        if content_length is not None and content_length > max_body_bytes:
            status, headers, body = _response(413, _PAYLOAD_TOO_LARGE)
            start_response(status, headers)
            return body

        input_stream = environ["wsgi.input"]
        limit = max_body_bytes + 1 if content_length is None else content_length
        raw_body = bytearray()
        while len(raw_body) < limit:
            chunk = input_stream.read(limit - len(raw_body))
            if not chunk:
                break
            raw_body.extend(chunk)
        if len(raw_body) > max_body_bytes:
            status, headers, response_body = _response(413, _PAYLOAD_TOO_LARGE)
            start_response(status, headers)
            return response_body

        request_headers = {
            name[5:].replace("_", "-"): value
            for name, value in environ.items()
            if name.startswith("HTTP_")
        }
        for name in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            value = environ.get(name)
            if value is not None:
                request_headers[name.replace("_", "-")] = value

        response = dispatcher.handle(bytes(raw_body), request_headers)
        status, headers, response_body = _response(response.status, response.body)
        start_response(status, headers)
        return response_body

    return app


__all__ = ["create_wsgi_app"]
