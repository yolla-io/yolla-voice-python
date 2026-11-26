from collections.abc import Mapping
from typing import Any, TypeAlias

from ..models import BalanceEvent, CallEvent, EventEnvelope, QualityEvent, TestEvent


class UnknownWebhookEvent(EventEnvelope):
    data: Mapping[str, Any]


KnownWebhookEvent: TypeAlias = BalanceEvent | CallEvent | QualityEvent | TestEvent
WebhookEvent: TypeAlias = KnownWebhookEvent | UnknownWebhookEvent

_CALL_EVENT_TYPES = {
    "call.initiated",
    "call.answered",
    "call.held",
    "call.unheld",
    "call.hold_failed",
    "call.completed",
    "call.expired",
}


def parse_event(payload: Mapping[str, Any]) -> WebhookEvent:
    envelope = EventEnvelope.model_validate(payload)
    if envelope.type in _CALL_EVENT_TYPES:
        return CallEvent.model_validate(payload)
    if envelope.type == "call.quality":
        return QualityEvent.model_validate(payload)
    if envelope.type == "balance.low":
        return BalanceEvent.model_validate(payload)
    if envelope.type == "webhook.test":
        return TestEvent.model_validate(payload)
    return UnknownWebhookEvent.model_validate(payload)
