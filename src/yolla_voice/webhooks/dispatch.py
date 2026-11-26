import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from ..errors import WebhookVerificationError
from .events import KnownWebhookEvent, UnknownWebhookEvent
from .secret import WebhookSecret
from .verify import DEFAULT_TOLERANCE, verify_webhook

_EventCallback = Callable[[KnownWebhookEvent], object]
_UnhandledCallback = Callable[[UnknownWebhookEvent], object]
_ErrorCallback = Callable[[Exception], object]
_Status = Literal[200, 401, 500]


@dataclass(frozen=True)
class WebhookResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


def _response(status: _Status) -> WebhookResponse:
    if status == 200:
        body = b'{"received":true}'
    elif status == 401:
        body = b'{"error":"webhook_verification_failed"}'
    else:
        body = b'{"error":"webhook_callback_failed"}'
    return WebhookResponse(
        status=status,
        headers={"Content-Type": "application/json"},
        body=body,
    )


def _reject_coroutine_callbacks(
    **callbacks: _EventCallback | _UnhandledCallback | _ErrorCallback | None,
) -> None:
    for name, callback in callbacks.items():
        if callback is not None and inspect.iscoroutinefunction(callback):
            raise TypeError(f"{name} must not be a coroutine function for WebhookDispatcher")


def _close_awaitable(awaitable: Awaitable[object]) -> None:
    try:
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
    except Exception:  # noqa: BLE001, S110
        pass


class WebhookDispatcher:
    def __init__(
        self,
        secret: WebhookSecret | None = None,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        on: _EventCallback | None = None,
        on_unhandled: _UnhandledCallback | None = None,
        on_error: _ErrorCallback | None = None,
    ) -> None:
        _reject_coroutine_callbacks(on=on, on_unhandled=on_unhandled, on_error=on_error)
        self._secret = secret
        self._tolerance = tolerance
        self._on = on
        self._on_unhandled = on_unhandled
        self._on_error = on_error

    def handle(self, raw_body: bytes | str, headers: Mapping[str, str]) -> WebhookResponse:
        try:
            event = verify_webhook(
                raw_body,
                headers,
                secret=self._secret,
                tolerance=self._tolerance,
            )
        except WebhookVerificationError:
            return _response(401)

        try:
            if isinstance(event, UnknownWebhookEvent):
                if self._on_unhandled is None:
                    return _response(200)
                result = self._on_unhandled(event)
            else:
                if self._on is None:
                    return _response(200)
                result = self._on(event)
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


class AsyncWebhookDispatcher:
    def __init__(
        self,
        secret: WebhookSecret | None = None,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        on: _EventCallback | None = None,
        on_unhandled: _UnhandledCallback | None = None,
        on_error: _ErrorCallback | None = None,
    ) -> None:
        self._secret = secret
        self._tolerance = tolerance
        self._on = on
        self._on_unhandled = on_unhandled
        self._on_error = on_error

    async def handle(self, raw_body: bytes | str, headers: Mapping[str, str]) -> WebhookResponse:
        try:
            event = verify_webhook(
                raw_body,
                headers,
                secret=self._secret,
                tolerance=self._tolerance,
            )
        except WebhookVerificationError:
            return _response(401)

        try:
            if isinstance(event, UnknownWebhookEvent):
                if self._on_unhandled is None:
                    return _response(200)
                result = self._on_unhandled(event)
            else:
                if self._on is None:
                    return _response(200)
                result = self._on(event)
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


__all__ = ["AsyncWebhookDispatcher", "WebhookDispatcher", "WebhookResponse"]
