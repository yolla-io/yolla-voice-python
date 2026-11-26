from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from yolla_voice.models import BalanceEvent, CallEvent, QualityEvent
from yolla_voice.models import TestEvent as GeneratedTestEvent
from yolla_voice.webhooks import UnknownWebhookEvent, parse_event

ENVELOPE = {
    "id": "evt_1",
    "seq": 4,
    "createdAt": "2026-11-23T10:15:00.000Z",
}
CALL = {
    "id": "call_1",
    "createdAt": "2026-11-23T10:00:00.000Z",
    "expiresAt": "2026-11-23T11:00:00.000Z",
    "externalUserId": "user-ü-42",
    "from": "14155550199",
    "status": "completed",
    "to": "14155550100",
}
MONEY = {"amount": "1.25", "currency": "USD"}


@pytest.mark.parametrize(
    ("event_type", "data", "model_type"),
    [
        ("webhook.test", {}, GeneratedTestEvent),
        ("call.completed", {"call": CALL}, CallEvent),
        (
            "call.quality",
            {"callId": "call_1", "externalUserId": "user-1", "quality": {}},
            QualityEvent,
        ),
        (
            "balance.low",
            {"available": MONEY, "balance": MONEY, "billingMode": "prepaid"},
            BalanceEvent,
        ),
    ],
)
def test_known_events_parse_to_generated_models(event_type, data, model_type):
    payload = {**ENVELOPE, "type": event_type, "data": data}
    if event_type == "webhook.test":
        payload["seq"] = 0

    event = parse_event(payload)

    assert isinstance(event, model_type)
    assert event.type == event_type
    assert event.created_at.utcoffset() is not None


def test_unknown_event_retains_envelope_original_data_and_extra_fields():
    data = {"future": [1, {"nested": True}]}
    payload = {**ENVELOPE, "type": "call.future", "data": data, "futureField": "kept"}

    event = parse_event(payload)

    assert isinstance(event, UnknownWebhookEvent)
    assert isinstance(event.data, Mapping)
    assert event.data == data
    assert event.id == "evt_1"
    assert event.seq == 4
    assert event.model_extra["futureField"] == "kept"


@pytest.mark.parametrize("data", [None, [], "not a mapping", 1])
def test_unknown_event_rejects_non_mapping_data(data):
    with pytest.raises(ValidationError):
        parse_event({**ENVELOPE, "type": "call.future", "data": data})


def test_invalid_known_event_does_not_fall_back_to_unknown():
    payload = {**ENVELOPE, "type": "webhook.test", "seq": 4, "data": {}}

    with pytest.raises(ValidationError):
        parse_event(payload)
