import hashlib
import hmac
import json
import traceback

import pytest

from yolla_voice.errors import WebhookVerificationError
from yolla_voice.models import TestEvent as GeneratedTestEvent
from yolla_voice.webhooks import sign_webhook, verify_webhook

TIMESTAMP = 1700000000
SECRET = "whsec_test"
BODY = b'{"id":"evt_test","type":"webhook.test","seq":0,"createdAt":"2026-11-23T10:15:00.000Z","data":{}}'
SIGNATURE = "v1=7b6fdffeec4f9fb2759d6bcbd22d8c35a73435790b58617d5041b0f1df059a19"


def headers_for(signature=SIGNATURE, timestamp=str(TIMESTAMP)):
    return {
        "x-voice-timestamp": timestamp,
        "X-VOICE-SIGNATURE": signature,
    }


def signature_for(body, secret=SECRET):
    if isinstance(body, str):
        body = body.encode("utf-8")
    digest = hmac.new(
        secret.encode("utf-8"), f"{TIMESTAMP}.".encode("ascii") + body, hashlib.sha256
    ).hexdigest()
    return f"v1={digest}"


def assert_reason(reason, body=BODY, headers=None, **kwargs):
    kwargs.setdefault("secret", SECRET)
    kwargs.setdefault("now", TIMESTAMP)
    with pytest.raises(WebhookVerificationError) as caught:
        verify_webhook(body, headers_for() if headers is None else headers, **kwargs)
    assert caught.value.reason == reason
    return caught.value


def test_known_hmac_vector_and_case_insensitive_headers():
    event = verify_webhook(BODY, headers_for(), secret=SECRET, now=TIMESTAMP)

    assert isinstance(event, GeneratedTestEvent)
    assert event.id == "evt_test"
    assert event.type == "webhook.test"
    assert SIGNATURE.startswith("v1=")


def test_utf8_string_and_bytes_bodies_are_equivalent():
    text = BODY.decode("utf-8")

    from_bytes = verify_webhook(BODY, headers_for(), secret=SECRET, now=TIMESTAMP)
    from_string = verify_webhook(text, headers_for(), secret=SECRET, now=TIMESTAMP)

    assert from_string == from_bytes


def test_changed_raw_byte_is_rejected_before_json_parsing():
    changed = BODY.replace(b'"seq":0', b'"seq":1')

    assert_reason("bad_signature", body=changed)
    assert_reason("bad_signature", body=b"not json")


@pytest.mark.parametrize("offset", [-300, 0, 300])
def test_timestamp_tolerance_boundary_is_inclusive(offset):
    event = verify_webhook(BODY, headers_for(), secret=SECRET, now=TIMESTAMP + offset)

    assert event.id == "evt_test"


@pytest.mark.parametrize("offset", [-301, 301])
def test_stale_timestamp_is_rejected_in_both_directions(offset):
    assert_reason("stale_timestamp", now=TIMESTAMP + offset)


def test_custom_tolerance_allows_a_wider_window():
    event = verify_webhook(BODY, headers_for(), secret=SECRET, tolerance=600, now=TIMESTAMP + 301)

    assert event.id == "evt_test"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Voice-Signature": SIGNATURE},
        {"X-Voice-Timestamp": str(TIMESTAMP)},
        {"X-Voice-Timestamp": "", "X-Voice-Signature": SIGNATURE},
        {"X-Voice-Timestamp": str(TIMESTAMP), "X-Voice-Signature": ""},
    ],
)
def test_missing_or_empty_headers_are_rejected(headers):
    assert_reason("missing_header", headers=headers)


@pytest.mark.parametrize("timestamp", ["abc", "12.5", "1e9", "-1", "１２"])
def test_malformed_timestamp_is_rejected(timestamp):
    assert_reason("missing_header", headers=headers_for(timestamp=timestamp))


@pytest.mark.parametrize(
    "signature",
    [
        SIGNATURE[3:],
        "v1=",
        "v1=xyz",
        f"v1={'0' * 63}",
        f"v1={'0' * 65}",
        f"v1={'g' * 64}",
        f"v1={SIGNATURE[3:].upper()}",
        f"v1={'0' * 64}",
    ],
)
def test_bad_non_hex_uppercase_and_differently_sized_signatures_are_rejected(signature):
    assert_reason("bad_signature", headers=headers_for(signature=signature))


@pytest.mark.parametrize("secrets", [(SECRET, "old"), ("old", SECRET)])
def test_any_secret_in_rotation_can_authenticate(secrets):
    event = verify_webhook(BODY, headers_for(), secret=secrets, now=TIMESTAMP)

    assert event.id == "evt_test"


def test_rotation_with_no_matching_secret_is_rejected():
    assert_reason("bad_signature", secret=("old", "older"))


def test_authenticated_invalid_json_is_invalid_payload():
    assert_reason(
        "invalid_payload", body=b"not json", headers=headers_for(signature_for(b"not json"))
    )


def test_authenticated_invalid_utf8_is_invalid_payload_not_unicode_error():
    signed = sign_webhook(
        b"\xff\xfe", secret=SECRET, timestamp=TIMESTAMP, delivery_id="dlv_invalid_utf8"
    )

    with pytest.raises(WebhookVerificationError) as caught:
        verify_webhook(signed.body, signed.headers, secret=SECRET, now=TIMESTAMP)

    assert caught.value.reason == "invalid_payload"
    assert str(caught.value) == "Webhook body is not valid JSON"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        [1],
        "text",
        1,
        {},
        {"id": "evt_1"},
        {"type": "webhook.test"},
        {"id": 1, "type": "webhook.test"},
        {"id": "evt_1", "type": 1},
        {
            "id": "evt_1",
            "type": "webhook.test",
            "seq": 1,
            "createdAt": "2026-11-23T10:15:00.000Z",
            "data": {},
        },
    ],
)
def test_authenticated_json_shape_and_known_model_failures_are_invalid_payload(payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    assert_reason("invalid_payload", body=body, headers=headers_for(signature_for(body)))


@pytest.mark.parametrize("body", [{"id": "evt_test"}, [1, 2, 3]])
def test_parsed_mappings_and_lists_are_rejected_as_raw_bodies(body):
    with pytest.raises(TypeError) as caught:
        verify_webhook(body, headers_for(), secret=SECRET, now=TIMESTAMP)

    assert "raw request bytes" in str(caught.value)
    assert "parsed" in str(caught.value)


@pytest.mark.parametrize("secret", ["", []])
def test_explicit_empty_secret_does_not_use_environment_for_verification(secret, monkeypatch):
    monkeypatch.setenv("YOLLA_WEBHOOK_SECRET", SECRET)

    with pytest.raises(ValueError, match="non-empty"):
        verify_webhook(BODY, headers_for(), secret=secret, now=TIMESTAMP)


def test_negative_tolerance_fails_before_verification():
    with pytest.raises(ValueError, match="tolerance"):
        verify_webhook(BODY, headers_for(), secret=SECRET, tolerance=-1, now=TIMESTAMP)


def test_invalid_payload_traceback_does_not_expose_authenticated_body_secrets():
    payload = {
        "id": "evt_test",
        "type": "webhook.test",
        "seq": 1,
        "createdAt": "2026-11-23T10:15:00.000Z",
        "data": {},
        "secret": SECRET,
        "signature": SIGNATURE,
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    error = assert_reason("invalid_payload", body=body, headers=headers_for(signature_for(body)))
    rendered = "".join(traceback.format_exception(error))

    assert str(error) == "Webhook body is not a valid event"
    assert repr(error) == "WebhookVerificationError('Webhook body is not a valid event')"
    assert error.__suppress_context__ is True
    assert SECRET not in rendered
    assert SIGNATURE not in rendered
    assert SIGNATURE[3:] not in rendered


def test_exact_verification_error_output_redacts_actual_secret_and_signatures():
    received = f"v1={'0' * 64}"

    error = assert_reason("bad_signature", headers=headers_for(signature=received))

    assert str(error) == "Webhook signature does not match"
    assert repr(error) == "WebhookVerificationError('Webhook signature does not match')"
    rendered = str(error) + repr(error)
    assert SECRET not in rendered
    assert SIGNATURE not in rendered
    assert SIGNATURE[3:] not in rendered
    assert received not in rendered
    assert received[3:] not in rendered


@pytest.mark.parametrize("now", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_now_is_rejected_instead_of_skipping_staleness(now):
    signed = sign_webhook(b"{}", secret=SECRET, timestamp=1)

    with pytest.raises(ValueError, match="now must be a finite number"):
        verify_webhook(signed.body, signed.headers, secret=SECRET, now=now)
