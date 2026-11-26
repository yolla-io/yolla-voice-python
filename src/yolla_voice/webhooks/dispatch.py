import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..errors import WebhookVerificationError
from .events import WebhookEvent
from .secret import WebhookSecret, resolve_webhook_secret
from .verify import DEFAULT_TOLERANCE, verify_webhook

# Handlers receive the event model that matches their key, such as `CallEvent` for
# "call.completed". The mapping is keyed by the wire event type.
EventHandler = Callable[[Any], object]
EventHandlers = Mapping[str, EventHandler]
UnhandledCallback = Callable[[WebhookEvent], object]
ErrorCallback = Callable[[Exception], object]
_Status = Literal[200, 401, 500]


@dataclass(frozen=True)
class WebhookResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


_BODIES: dict[_Status, bytes] = {
    200: b'{"received":true}',
    401: b'{"error":"invalid signature"}',
    500: b'{"error":"handler failed"}',
}


def _response(status: _Status) -> WebhookResponse:
    return WebhookResponse(
        status=status,
        headers={"Content-Type": "application/json"},
        body=_BODIES[status],
    )


def _close_awaitable(awaitable: Awaitable[object]) -> None:
    try:
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
    except Exception:  # noqa: BLE001, S110
        pass


def _handlers(on: EventHandlers | None) -> dict[str, EventHandler]:
    if on is None:
        return {}
    if not isinstance(on, Mapping):
        raise TypeError("on must be a mapping of event type to handler")
    for event_type, handler in on.items():
        if not isinstance(event_type, str) or not callable(handler):
            raise TypeError("on must map event type strings to callables")
    return dict(on)


class _BaseDispatcher:
    def __init__(
        self,
        secret: WebhookSecret | None,
        tolerance: float,
        on: EventHandlers | None,
        on_unhandled: UnhandledCallback | None,
        on_error: ErrorCallback | None,
    ) -> None:
        self._secret = resolve_webhook_secret(secret)
        self._tolerance = tolerance
        self._on = _handlers(on)
        self._on_unhandled = on_unhandled
        self._on_error = on_error

    def _verify(
        self, raw_body: bytes | str, headers: Mapping[str, str]
    ) -> WebhookEvent | Exception:
        try:
            return verify_webhook(
                raw_body,
                headers,
                secret=self._secret,
                tolerance=self._tolerance,
            )
        except Exception as error:  # noqa: BLE001
            return error

    def _callback(self, event: WebhookEvent) -> Callable[[Any], object] | None:
        handler = self._on.get(event.type)
        return handler if handler is not None else self._on_unhandled

    @staticmethod
    def _rejection_status(error: Exception) -> _Status:
        return 401 if isinstance(error, WebhookVerificationError) else 500


class WebhookDispatcher(_BaseDispatcher):
    def __init__(
        self,
        secret: WebhookSecret | None = None,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        on: EventHandlers | None = None,
        on_unhandled: UnhandledCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        super().__init__(secret, tolerance, on, on_unhandled, on_error)
        callbacks: dict[str, object] = {f"on[{key!r}]": value for key, value in self._on.items()}
        callbacks.update(on_unhandled=on_unhandled, on_error=on_error)
        for name, callback in callbacks.items():
            if callback is not None and inspect.iscoroutinefunction(callback):
                raise TypeError(f"{name} must not be a coroutine function for WebhookDispatcher")

    def handle(self, raw_body: bytes | str, headers: Mapping[str, str]) -> WebhookResponse:
        event = self._verify(raw_body, headers)
        if isinstance(event, Exception):
            self._report_error(event)
            return _response(self._rejection_status(event))

        try:
            callback = self._callback(event)
            if callback is not None:
                result = callback(event)
                if inspect.isawaitable(result):
                    _close_awaitable(result)
                    raise TypeError("Synchronous webhook callbacks must not return awaitables")
        except Exception as error:  # noqa: BLE001
            self._report_error(error)
            return _response(500)
        return _response(200)

    def _report_error(self, error: Exception) -> None:
        if self._on_error is None:
            return
        try:
            result = self._on_error(error)
            if inspect.isawaitable(result):
                _close_awaitable(result)
        except Exception:  # noqa: BLE001, S110
            pass


class AsyncWebhookDispatcher(_BaseDispatcher):
    def __init__(
        self,
        secret: WebhookSecret | None = None,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        on: EventHandlers | None = None,
        on_unhandled: UnhandledCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        super().__init__(secret, tolerance, on, on_unhandled, on_error)

    async def handle(self, raw_body: bytes | str, headers: Mapping[str, str]) -> WebhookResponse:
        event = self._verify(raw_body, headers)
        if isinstance(event, Exception):
            await self._report_error(event)
            return _response(self._rejection_status(event))

        try:
            callback = self._callback(event)
            if callback is not None:
                result = callback(event)
                if inspect.isawaitable(result):
                    await result
        except Exception as error:  # noqa: BLE001
            await self._report_error(error)
            return _response(500)
        return _response(200)

    async def _report_error(self, error: Exception) -> None:
        if self._on_error is None:
            return
        try:
            result = self._on_error(error)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001, S110
            pass


__all__ = [
    "AsyncWebhookDispatcher",
    "ErrorCallback",
    "EventHandler",
    "EventHandlers",
    "UnhandledCallback",
    "WebhookDispatcher",
    "WebhookResponse",
]
