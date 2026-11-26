import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias
from uuid import uuid4

from pydantic import BaseModel

from .headers import DELIVERY_ID_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER
from .secret import WebhookSecret, resolve_webhook_secret

WebhookPayload: TypeAlias = bytes | str | Mapping[str, Any] | BaseModel


@dataclass(frozen=True, slots=True, repr=False)
class SignedWebhook:
    body: bytes
    headers: dict[str, str]

    def __repr__(self) -> str:
        return f"SignedWebhook(body=<{len(self.body)} bytes>, headers=<redacted>)"


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    signed_payload = timestamp.encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def _payload_bytes(payload: WebhookPayload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, BaseModel):
        serializable = payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
    elif isinstance(payload, Mapping):
        serializable = dict(payload)
    else:
        raise TypeError("Webhook payload must be bytes, a UTF-8 string, a mapping, or a model")
    try:
        serialized = json.dumps(serializable, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError):
        raise TypeError("Webhook payload is not JSON serializable") from None
    return serialized.encode("utf-8")


def sign_webhook(
    payload: WebhookPayload,
    *,
    secret: WebhookSecret | None = None,
    timestamp: int | None = None,
    delivery_id: str | None = None,
) -> SignedWebhook:
    signing_secret = resolve_webhook_secret(secret)[0]
    body = _payload_bytes(payload)
    timestamp_value = str(int(time.time()) if timestamp is None else timestamp)
    signature = compute_signature(signing_secret, timestamp_value, body)
    delivery = f"dlv_{uuid4().hex}" if delivery_id is None else delivery_id
    return SignedWebhook(
        body=body,
        headers={
            TIMESTAMP_HEADER: timestamp_value,
            SIGNATURE_HEADER: f"v1={signature}",
            DELIVERY_ID_HEADER: delivery,
        },
    )
