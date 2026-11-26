import json
import re
import time

import pytest

from yolla_voice.models import CreateCallRequest
from yolla_voice.webhooks import sign_webhook, verify_webhook

TIMESTAMP = 1700000000
SECRET = "whsec_test"
BODY = b'{"id":"evt_test","type":"webhook.test","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{}}'
SIGNATURE = "v1=7b6fdffeec4f9fb2759d6bcbd22d8c35a73435790b58617d5041b0f1df059a19"


def test_known_vector_has_exact_bytes_headers_and_v1_lowercase_hex():
    signed = sign_webhook(BODY, secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_deterministic")

    assert signed.body is BODY
    assert signed.headers == {
        "X-Voice-Timestamp": "1700000000",
        "X-Voice-Signature": SIGNATURE,
        "X-Voice-Delivery-Id": "dlv_deterministic",
    }
    assert re.fullmatch(r"v1=[0-9a-f]{64}", signed.headers["X-Voice-Signature"])


def test_mapping_serialization_is_compact_and_deterministic():
    payload = {"id": "evt_1", "type": "call.future", "data": {"message": "ü"}}

    first = sign_webhook(
        payload, secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_deterministic"
    )
    second = sign_webhook(
        payload, secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_deterministic"
    )

    assert first.body == '{"id":"evt_1","type":"call.future","data":{"message":"ü"}}'.encode()
    assert first.headers == second.headers


def test_model_serialization_uses_wire_aliases_and_excludes_unset_fields():
    request = CreateCallRequest(to="14155550100", external_user_id="user-1")

    signed = sign_webhook(
        request, secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_deterministic"
    )

    assert json.loads(signed.body) == {"externalUserId": "user-1", "to": "14155550100"}
    assert b"external_user_id" not in signed.body
    assert b"maxDuration" not in signed.body


def test_string_and_equivalent_utf8_bytes_produce_the_same_signature():
    text = BODY.decode("utf-8")

    from_string = sign_webhook(
        text, secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_deterministic"
    )
    from_bytes = sign_webhook(
        BODY, secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_deterministic"
    )

    assert from_string.body == BODY
    assert from_string.headers == from_bytes.headers


def test_default_timestamp_is_unix_seconds_and_delivery_ids_are_random_uuids():
    before = int(time.time())
    first = sign_webhook("{}", secret=SECRET)
    second = sign_webhook("{}", secret=SECRET)
    after = int(time.time())

    assert before <= int(first.headers["X-Voice-Timestamp"]) <= after
    first_delivery = first.headers["X-Voice-Delivery-Id"]
    second_delivery = second.headers["X-Voice-Delivery-Id"]
    assert re.fullmatch(r"dlv_[0-9a-f]{32}", first_delivery)
    assert re.fullmatch(r"dlv_[0-9a-f]{32}", second_delivery)
    assert first_delivery != second_delivery


def test_rotation_signs_with_first_secret():
    signed = sign_webhook(
        BODY, secret=(SECRET, "old"), timestamp=TIMESTAMP, delivery_id="dlv_deterministic"
    )

    assert signed.headers["X-Voice-Signature"] == SIGNATURE


def test_environment_secret_fallback(monkeypatch):
    monkeypatch.setenv("YOLLA_WEBHOOK_SECRET", SECRET)

    signed = sign_webhook(BODY, timestamp=TIMESTAMP, delivery_id="dlv_deterministic")
    event = verify_webhook(signed.body, signed.headers, now=TIMESTAMP)

    assert signed.headers["X-Voice-Signature"] == SIGNATURE
    assert event.id == "evt_test"


@pytest.mark.parametrize("secret", [None, "", []])
def test_missing_and_empty_secrets_fail_at_operation_creation(secret, monkeypatch):
    monkeypatch.delenv("YOLLA_WEBHOOK_SECRET", raising=False)

    with pytest.raises(ValueError) as caught:
        sign_webhook("{}", secret=secret)

    assert "YOLLA_WEBHOOK_SECRET" in str(caught.value)
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize("secret", [(SECRET, ""), ("", SECRET), [SECRET, 1]])
def test_rotation_rejects_empty_or_non_string_entries(secret):
    with pytest.raises((TypeError, ValueError)) as caught:
        sign_webhook("{}", secret=secret)

    assert SECRET not in str(caught.value)


def test_signed_webhook_repr_and_str_redact_actual_signature_and_secret():
    signed = sign_webhook(BODY, secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_deterministic")

    rendered = repr(signed) + str(signed)
    assert SECRET not in rendered
    assert SIGNATURE not in rendered
    assert SIGNATURE[3:] not in rendered
    assert "redacted" in rendered
