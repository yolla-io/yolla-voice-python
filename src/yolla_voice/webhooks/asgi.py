from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, TypeAlias

from .dispatch import AsyncWebhookDispatcher

_Scope: TypeAlias = MutableMapping[str, Any]
_Message: TypeAlias = MutableMapping[str, Any]
_Receive: TypeAlias = Callable[[], Awaitable[_Message]]
_Send: TypeAlias = Callable[[_Message], Awaitable[None]]
_ASGIApplication: TypeAlias = Callable[[_Scope, _Receive, _Send], Awaitable[None]]

_METHOD_NOT_ALLOWED = b'{"error":"method_not_allowed"}'
_PAYLOAD_TOO_LARGE = b'{"error":"payload_too_large"}'


async def _send_response(
    send: _Send,
    status: int,
    body: bytes,
    *,
    allow_post: bool = False,
) -> None:
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if allow_post:
        headers.append((b"allow", b"POST"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _run_lifespan(receive: _Receive, send: _Send) -> None:
    while True:
        message = await receive()
        if message.get("type") == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message.get("type") == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


def create_asgi_app(
    dispatcher: AsyncWebhookDispatcher,
    *,
    max_body_bytes: int = 1_048_576,
) -> _ASGIApplication:
    async def app(scope: _Scope, receive: _Receive, send: _Send) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await _run_lifespan(receive, send)
            return
        if scope_type == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope_type != "http":
            raise ValueError(f"Unsupported ASGI scope type: {scope_type!r}")

        if scope.get("method") != "POST":
            await _send_response(send, 405, _METHOD_NOT_ALLOWED, allow_post=True)
            return

        headers = {
            name.decode("latin-1"): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        content_length = next(
            (value for name, value in headers.items() if name.lower() == "content-length"),
            None,
        )
        try:
            if content_length is not None and int(content_length) > max_body_bytes:
                await _send_response(send, 413, _PAYLOAD_TOO_LARGE)
                return
        except ValueError:
            pass

        body = bytearray()
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            remaining = max_body_bytes + 1 - len(body)
            chunk = message.get("body", b"")
            body.extend(chunk[:remaining])
            if len(body) > max_body_bytes:
                await _send_response(send, 413, _PAYLOAD_TOO_LARGE)
                return
            if not message.get("more_body", False):
                break

        response = await dispatcher.handle(bytes(body), headers)
        await _send_response(send, response.status, response.body)

    return app


__all__ = ["create_asgi_app"]
