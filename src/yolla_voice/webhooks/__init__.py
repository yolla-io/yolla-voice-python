from collections.abc import Mapping

from .events import KnownWebhookEvent, UnknownWebhookEvent, WebhookEvent, parse_event
from .secret import WebhookSecret
from .sign import SignedWebhook, WebhookPayload, sign_webhook
from .verify import DEFAULT_TOLERANCE, verify_webhook


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
    "KnownWebhookEvent",
    "SignedWebhook",
    "UnknownWebhookEvent",
    "WebhookEvent",
    "WebhookSecret",
    "Webhooks",
    "parse_event",
    "sign_webhook",
    "verify_webhook",
]
