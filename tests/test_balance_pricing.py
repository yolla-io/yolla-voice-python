import json

import httpx

from yolla_voice import AsyncYollaVoice, Balance, NumberPrice, YollaVoice

API_KEY = "test-api-key"
BASE_URL = "https://platform.yolla.io/api"


def json_response(body):
    return httpx.Response(
        200,
        content=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )


def balance_payload():
    return {
        "available": {"amount": "9.50", "currency": "USD"},
        "balance": {"amount": "10.00", "currency": "USD"},
        "billingMode": "prepaid",
        "creditLimit": None,
    }


def price_payload():
    return {
        "number": "14155550100",
        "country": "US",
        "rate": {
            "prefix": "1",
            "perMinute": {"amount": "0.01", "currency": "USD"},
            "firstIncrementSec": 1,
            "nextIncrementSec": 1,
        },
    }


def test_balance_and_pricing_get_typed_models_and_encode_number():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/api/v1/balance":
            return json_response(balance_payload())
        return json_response(price_payload())

    with YollaVoice(api_key=API_KEY, transport=httpx.MockTransport(handler)) as client:
        balance = client.balance.get(timeout=2.0, max_retries=0)
        price = client.pricing.get_number_price("1415/55 0100", timeout=3.0, max_retries=0)

    assert isinstance(balance, Balance)
    assert balance.available.amount == "9.50"
    assert isinstance(price, NumberPrice)
    assert price.rate.per_minute.amount == "0.01"
    assert str(seen[0].url) == f"{BASE_URL}/v1/balance"
    assert str(seen[1].url) == f"{BASE_URL}/v1/pricing/numbers/1415%2F55%200100"
    assert seen[0].extensions["timeout"]["read"] == 2.0
    assert seen[1].extensions["timeout"]["read"] == 3.0


async def test_async_balance_and_pricing_match_sync_behavior():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/api/v1/balance":
            return json_response(balance_payload())
        return json_response(price_payload())

    async with AsyncYollaVoice(api_key=API_KEY, transport=httpx.MockTransport(handler)) as client:
        balance = await client.balance.get(timeout=2.0, max_retries=0)
        price = await client.pricing.get_number_price("1415/55 0100", timeout=3.0, max_retries=0)

    assert isinstance(balance, Balance)
    assert balance.available.amount == "9.50"
    assert isinstance(price, NumberPrice)
    assert price.rate.per_minute.amount == "0.01"
    assert str(seen[0].url) == f"{BASE_URL}/v1/balance"
    assert str(seen[1].url) == f"{BASE_URL}/v1/pricing/numbers/1415%2F55%200100"
    assert seen[0].extensions["timeout"]["read"] == 2.0
    assert seen[1].extensions["timeout"]["read"] == 3.0
