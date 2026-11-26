from collections.abc import Mapping

from .asgi import create_asgi_app
from .dispatch import (
    AsyncWebhookDispatcher,
    ErrorCallback,
    EventHandlers,
    UnhandledCallback,
    WebhookDispatcher,
    WebhookResponse,
)
from .events import KnownWebhookEvent, UnknownWebhookEvent, WebhookEvent, parse_event
from .secret import WebhookSecret
from .sign import SignedWebhook, WebhookPayload, sign_webhook
from .verify import DEFAULT_TOLERANCE, verify_webhook
from .wsgi import create_wsgi_app


class Webhooks:
    def __init__(self, secret: WebhookSecret | None = None) -> None:
        self._secret = secret

    def __repr__(self) -> str:
        return "Webhooks()"

    def verify(
        self,
        raw_body: bytes | str,
        headers: Mapping[str, str],
        *,
        secret: WebhookSecret | None = None,
        tolerance: float = DEFAULT_TOLERANCE,
        now: float | None = None,
    ) -> WebhookEvent:
        resolved_secret = self._secret if secret is None else secret
        return verify_webhook(
            raw_body,
            headers,
            secret=resolved_secret,
            tolerance=tolerance,
            now=now,
        )

    def create_dispatcher(
        self,
        *,
        secret: WebhookSecret | None = None,
        tolerance: float = DEFAULT_TOLERANCE,
        on: EventHandlers | None = None,
        on_unhandled: UnhandledCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> WebhookDispatcher:
        resolved_secret = self._secret if secret is None else secret
        return WebhookDispatcher(
            secret=resolved_secret,
            tolerance=tolerance,
            on=on,
            on_unhandled=on_unhandled,
            on_error=on_error,
        )

    def create_async_dispatcher(
        self,
        *,
        secret: WebhookSecret | None = None,
        tolerance: float = DEFAULT_TOLERANCE,
        on: EventHandlers | None = None,
        on_unhandled: UnhandledCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> AsyncWebhookDispatcher:
        resolved_secret = self._secret if secret is None else secret
        return AsyncWebhookDispatcher(
            secret=resolved_secret,
            tolerance=tolerance,
            on=on,
            on_unhandled=on_unhandled,
            on_error=on_error,
        )

    def sign(
        self,
        payload: WebhookPayload,
        *,
        secret: WebhookSecret | None = None,
        timestamp: int | None = None,
        delivery_id: str | None = None,
    ) -> SignedWebhook:
        resolved_secret = self._secret if secret is None else secret
        return sign_webhook(
            payload,
            secret=resolved_secret,
            timestamp=timestamp,
            delivery_id=delivery_id,
        )


__all__ = [
    "AsyncWebhookDispatcher",
    "ErrorCallback",
    "EventHandlers",
    "KnownWebhookEvent",
    "SignedWebhook",
    "UnhandledCallback",
    "UnknownWebhookEvent",
    "WebhookDispatcher",
    "WebhookEvent",
    "WebhookResponse",
    "WebhookSecret",
    "Webhooks",
    "create_asgi_app",
    "create_wsgi_app",
    "parse_event",
    "sign_webhook",
    "verify_webhook",
]
