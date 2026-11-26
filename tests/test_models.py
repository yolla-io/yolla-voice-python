from datetime import datetime

import pytest
from pydantic import ValidationError

from yolla_voice import models
from yolla_voice.generated.models import ListCallsResponse
from yolla_voice.models import Call, CallList, CallStatus, CreateCallRequest, Money


def test_request_uses_python_names_and_wire_aliases():
    request = CreateCallRequest(to="14155550100", from_="14155550199", external_user_id="u1")
    assert request.model_dump(by_alias=True, exclude_unset=True) == {
        "to": "14155550100",
        "from": "14155550199",
        "externalUserId": "u1",
    }
    assert request.model_config["populate_by_name"] is True
    assert request.model_config["extra"] == "allow"


def test_request_rejects_leading_plus_destination():
    with pytest.raises(ValidationError, match="String should match pattern"):
        CreateCallRequest(to="+14155550100", external_user_id="u1")


def test_request_rejects_leading_plus_e164():
    with pytest.raises(ValidationError, match="String should match pattern"):
        CreateCallRequest(to="14155550100", from_="+14155550199", external_user_id="u1")


def test_unknown_enum_value_survives():
    value = CallStatus("future_status")
    assert value.value == "future_status"
    assert str(value) == "future_status"


def test_extra_response_field_survives():
    money = Money.model_validate({"amount": "1.25", "currency": "USD", "futureField": 7})
    assert money.model_extra == {"futureField": 7}


def test_datetime_fields_are_timezone_aware():
    call = Call.model_validate(
        {
            "id": "call_1",
            "status": "created",
            "to": "14155550100",
            "from": "14155550199",
            "externalUserId": "u1",
            "createdAt": "2026-11-25T12:00:00Z",
            "expiresAt": "2026-11-25T13:00:00+00:00",
        }
    )
    assert isinstance(call.created_at, datetime)
    assert call.created_at.utcoffset() is not None
    assert call.expires_at.utcoffset() is not None


def test_monetary_amounts_remain_strings():
    money = Money.model_validate({"amount": "1.25", "currency": "USD"})
    assert money.amount == "1.25"
    assert isinstance(money.amount, str)


def test_call_list_aliases_list_calls_response():
    assert CallList is ListCallsResponse
    calls = CallList.model_validate({"items": [], "nextCursor": "next"})
    assert calls.next_cursor == "next"


@pytest.mark.parametrize(
    "name",
    [
        "Balance",
        "BalanceEvent",
        "Call",
        "CallEvent",
        "CallList",
        "CallStatus",
        "CreateCallRequest",
        "CreateCallResponse",
        "EndReason",
        "ErrorBody",
        "ErrorResponse",
        "EventEnvelope",
        "FinalStats",
        "GatewayRequest",
        "GatewayResponse",
        "IntervalStats",
        "Money",
        "NumberPrice",
        "QualityEvent",
        "QualitySummary",
        "Rate",
        "TestEvent",
    ],
)
def test_models_reexports_public_schemas(name):
    assert name in models.__all__
    assert getattr(models, name) is not None


def test_phone_number_fields_are_plain_strings():
    request = CreateCallRequest(to="14155550100", from_="14155550199", external_user_id="user-1")

    assert type(request.to) is str
    assert type(request.from_) is str
    assert request.model_dump(by_alias=True, exclude_unset=True)["to"] == "14155550100"
