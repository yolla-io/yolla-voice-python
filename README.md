# yolla-voice-python

Python server SDK for the Yolla Voice Reseller API: create and manage calls, read the balance and
number prices, and receive signed webhooks. Synchronous and asynchronous clients, typed Pydantic
models, and framework-independent ASGI and WSGI webhook endpoints.

> Pre-release (0.x). The API contract is still a draft, so minor versions may change the API.

## Installation

```sh
pip install yolla-voice-python
```

or `uv add yolla-voice-python`. The import package is `yolla_voice`.

## Quick start

```python
from yolla_voice import CreateCallRequest, YollaVoice

with YollaVoice(api_key="your-api-key") as client:
    created = client.calls.create(
        CreateCallRequest(to="14155550100", external_user_id="user-42"),
    )

    # Pass call_token to your mobile app. The app uses it to start the call.
    print(created.call.id, created.call.call_token, created.call.expires_at)
```

The asynchronous client has the same methods and arguments:

```python
import asyncio

from yolla_voice import AsyncYollaVoice, CreateCallRequest


async def main() -> None:
    async with AsyncYollaVoice() as client:
        created = await client.calls.create(
            CreateCallRequest(to="14155550100", external_user_id="user-42"),
        )
        print(created.call.id, created.call.call_token)


asyncio.run(main())
```

Runnable versions are in [`examples/`](examples).

## Configuration

```python
from yolla_voice import YollaVoice

client = YollaVoice(api_key="your-api-key", timeout=10.0, max_retries=3)
```

| Option           | Environment variable   | Default                         | Description                                          |
| ---------------- | ---------------------- | ------------------------------- | ---------------------------------------------------- |
| `api_key`        | `YOLLA_API_KEY`        | none                            | Reseller API key. Required.                          |
| `webhook_secret` | `YOLLA_WEBHOOK_SECRET` | none                            | Signing secret, or a list of secrets during rotation. |
| `timeout`        |                        | `30.0`                          | Timeout of one attempt, in seconds.                  |
| `max_retries`    |                        | `2`                             | Retries after a 429, 5xx, network error or timeout.  |
| `transport`      |                        | `httpx` default                 | Custom `httpx` transport, for proxies or tests.      |

Requests go to `https://platform.yolla.io/api`. The constructor raises `ValueError` when the API key
is missing. The API key and webhook secrets
never appear in exception messages or in the `repr` of the client or of any error.

A client owns a connection pool. Use it as a context manager, or call `close()` (`await aclose()`
for `AsyncYollaVoice`) when you are done. Create one client per process and share it.

Every request method takes keyword-only `timeout` and `max_retries` that override the client
defaults for that call:

```python
balance = client.balance.get(timeout=5.0, max_retries=0)
```

## Calls

```python
from yolla_voice import CreateCallRequest

# Create. The result says whether the call already existed for this idempotency key.
created = client.calls.create(
    CreateCallRequest(
        to="14155550100",
        from_="14155550199",  # optional caller id
        external_user_id="user-42",
        custom_params={"orderId": "A-1001"},
        max_duration=600,  # seconds, optional
    ),
    idempotency_key="order-A-1001",  # optional, a random UUID by default
)
call, replayed = created.call, created.replayed

current = client.calls.get(call.id)
client.calls.hold(call.id)
client.calls.unhold(call.id)
ended = client.calls.end(call.id)

# Balance and prices
balance = client.balance.get()  # billing_mode, balance, credit_limit, available
price = client.pricing.get_number_price("14155550100")  # number, country, rate
```

Phone numbers are digits only, without a leading `+`. Models use snake_case attributes and accept
either snake_case names or the API's camelCase names as input. Money values are exact decimal
strings (`balance.available.amount`), and timestamps are timezone-aware `datetime` objects. Fields
and enum values added to the API later are kept rather than rejected.

## Pagination

`calls.iter_all` yields every call of every page and fetches the next page only when you reach it.
`calls.list` returns one page.

```python
# Every call, fetching pages as needed
for call in client.calls.iter_all(status="completed", limit=100):
    print(call.id, call.duration)

# Page by page
page = client.calls.list(external_user_id="user-42")
while True:
    print(len(page.items))
    if not page.has_next_page:
        break
    page = page.next_page()
```

With `AsyncYollaVoice`, use `async for call in client.calls.iter_all(...)` and
`page = await page.next_page()`.

Filters: `status`, `external_user_id`, `from_`, `to`, `limit` (1 to 200), `cursor`. `from_` and `to`
take a timezone-aware `datetime` or an ISO 8601 string; a naive `datetime` raises `ValueError`.
Filters and per-request options apply to every page. A `cursor` you pass applies to the first page
only.

## Errors

All errors extend `YollaVoiceError` and carry `status`, `code` and `request_id`. Quote the
`request_id` in support requests.

| Class                      | When                                                      |
| -------------------------- | --------------------------------------------------------- |
| `ValidationError`          | 400, 422: malformed request or invalid parameters         |
| `AuthenticationError`      | 401: missing or invalid API key                           |
| `InsufficientBalanceError` | 402: not enough balance                                   |
| `PermissionError`          | 403: blocked reseller, user, destination or caller id     |
| `NotFoundError`            | 404: call not found                                       |
| `ConflictError`            | 409: idempotency conflict or wrong call state             |
| `RateLimitError`           | 429: rate limit or concurrent calls; has `retry_after`    |
| `ServerError`              | 5xx                                                       |
| `APIConnectionError`       | no response (DNS, TCP, TLS); the original is `__cause__`  |
| `APITimeoutError`          | no response within `timeout`; extends `APIConnectionError` |
| `WebhookVerificationError` | webhook failed verification; has `reason`                 |

A successful response that does not match the contract raises `YollaVoiceError` with code
`invalid_response`. `yolla_voice.ValidationError` and `yolla_voice.PermissionError` are SDK classes:
import them from `yolla_voice` explicitly. Invalid input to a model such as `CreateCallRequest`
raises Pydantic's own `pydantic.ValidationError` before any request is sent.

Branch on the class, then on `code` for the exact reason:

```python
from yolla_voice import ConflictError, CreateCallRequest, PermissionError, YollaVoiceError

try:
    client.calls.create(CreateCallRequest(to="14155550100", external_user_id="user-42"))
except PermissionError as error:
    if error.code == "destination_blocked":
        ...  # tell the user this destination is not available
except ConflictError as error:
    if error.code == "idempotency_conflict":
        ...  # the same idempotency key was used with different parameters
except YollaVoiceError as error:
    print(error.status, error.code, error.request_id)
```

## Retries and idempotency

The SDK retries a 429, a 5xx, a network error and a timeout, up to `max_retries` times, with
exponential backoff and full jitter (0.5 seconds doubling up to 8 seconds). It honors
`Retry-After`, up to 60 seconds. Other 4xx answers are never retried. When the retries run out, the
raised error is the one from the last attempt, with its `request_id`. Cancelling an `asyncio` task
stops the SDK at once, also during a backoff pause, and raises `asyncio.CancelledError` unchanged.

`calls.create` sends an `Idempotency-Key` header. The SDK generates one per call and reuses it on
its own retries, so a retried create never starts a second call. To make your own retries safe too,
pass the same `idempotency_key` (for example, your order id, up to 128 characters):

```python
created = client.calls.create(request, idempotency_key="order-A-1001")
if created.replayed:
    # The call was created by an earlier request with this key.
    # call_token may be spent or expired: check expires_at and create a new call if needed.
    print(created.call.expires_at)
```

`hold`, `unhold` and `end` are retried too. If the first attempt reached the API but the response
was lost, the retry can answer `409 invalid_call_state` (for example, a second `hold`). Treat it as
"already done" after reading the call with `calls.get`.

## Webhooks

The platform sends events to your endpoint as `POST` with a JSON body and these headers:

| Header                | Value                                                                  |
| --------------------- | ---------------------------------------------------------------------- |
| `X-Voice-Timestamp`   | Unix time in seconds                                                   |
| `X-Voice-Signature`   | `v1=` plus hex HMAC-SHA256 of `<timestamp>.<raw body>` with the secret |
| `X-Voice-Delivery-Id` | Id of this delivery attempt                                            |

Verification needs the raw body, exactly as received. Do not parse it first.

### Dispatchers

A dispatcher verifies a request, calls your handler for its event type, and returns the HTTP
response to send. `WebhookDispatcher` takes regular functions; `AsyncWebhookDispatcher` takes
`async` functions and regular functions.

```python
from yolla_voice import (
    AsyncWebhookDispatcher,
    BalanceEvent,
    CallEvent,
    WebhookEvent,
    WebhookVerificationError,
)


async def on_call_completed(event: CallEvent) -> None:
    print(event.data.call.id, event.data.call.billed_duration)


def on_balance_low(event: BalanceEvent) -> None:
    print(event.data.available.amount)


def on_unhandled(event: WebhookEvent) -> None:
    print("ignored", event.type)


def on_error(error: Exception) -> None:
    if isinstance(error, WebhookVerificationError):
        print("rejected:", error.reason)  # a wrong secret or clock skew shows up here


dispatcher = AsyncWebhookDispatcher(
    secret="your-webhook-secret",
    on={"call.completed": on_call_completed, "balance.low": on_balance_low},
    on_unhandled=on_unhandled,
    on_error=on_error,
)
```

`on` maps event types to handlers. Events without a handler, including types added after your SDK
version, go to `on_unhandled`. The dispatcher answers `200 {"received":true}`, `401` for a bad
signature or timestamp, and `500` when your handler raises. `on_error` receives the real error of
every `401` (a `WebhookVerificationError` with its `reason`) and of every `500`; the response body
never contains it, and an exception from `on_error` does not change the response.

`secret` defaults to `YOLLA_WEBHOOK_SECRET`. The dispatcher checks it when you create it and raises
`ValueError` if there is none, so a misconfigured service fails at startup. If you already created a
client with a `webhook_secret`, use `client.webhooks.create_dispatcher(on=...)` or
`client.webhooks.create_async_dispatcher(on=...)`.

### ASGI (FastAPI, Starlette, Quart, Django ASGI)

```python
from fastapi import FastAPI

from yolla_voice import create_asgi_app

app = FastAPI()
app.add_route("/webhooks/yolla", create_asgi_app(dispatcher), methods=["POST"])
```

With Starlette, use `Route("/webhooks/yolla", create_asgi_app(dispatcher), methods=["POST"])`. Prefer
an exact route over `mount`: a mounted app answers a `POST` without the trailing slash with a
redirect, which webhook deliveries do not follow.

### WSGI (Flask, Django, any WSGI server)

```python
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from yolla_voice import WebhookDispatcher, create_wsgi_app

webhooks = create_wsgi_app(WebhookDispatcher(on={"call.completed": print}))
flask_app = Flask(__name__)
flask_app.wsgi_app = DispatcherMiddleware(flask_app.wsgi_app, {"/webhooks/yolla": webhooks})
```

Both endpoints also answer `405` (with `Allow: POST`) for other methods and `413` for a body over
1 MiB, also when it arrives without a `Content-Length`. Pass `max_body_bytes` to change the limit.
The WSGI endpoint answers `411` when a request has no `Content-Length` and the server does not mark
the input as terminated.

### Other frameworks

Read the raw body yourself and call `handle`, which never raises for a bad request:

```python
from flask import Flask, request

from yolla_voice import WebhookDispatcher

app = Flask(__name__)
dispatcher = WebhookDispatcher(on={"call.completed": print})


@app.post("/webhooks/yolla")
def yolla_webhook():
    response = dispatcher.handle(request.get_data(), request.headers)
    return response.body, response.status, dict(response.headers)
```

### Verifying yourself

```python
from yolla_voice import (
    BalanceEvent,
    CallEvent,
    QualityEvent,
    UnknownWebhookEvent,
    WebhookVerificationError,
)

try:
    event = client.webhooks.verify(raw_body, headers)  # bytes or str, any header case
except WebhookVerificationError as error:
    print(error.reason)  # "missing_header", "bad_signature", "stale_timestamp", "invalid_payload"
else:
    if isinstance(event, CallEvent) and event.type == "call.completed":
        print(event.data.call.end_reason)
    elif isinstance(event, QualityEvent):
        print(event.data.quality.mos_estimate)
    elif isinstance(event, BalanceEvent):
        print(event.data.available.amount)
    elif isinstance(event, UnknownWebhookEvent):
        print("new event type", event.type, event.data)  # data is the raw mapping
```

`verify_webhook(raw_body, headers, secret=...)` does the same without a client; `secret` defaults to
`YOLLA_WEBHOOK_SECRET`. The timestamp must be within 5 minutes of your clock (`tolerance`, default
`300` seconds).

### Events

`call.initiated`, `call.answered`, `call.held`, `call.unheld`, `call.hold_failed`, `call.completed`,
`call.expired` (all `CallEvent`), `call.quality` (`QualityEvent`), `balance.low` (`BalanceEvent`),
`webhook.test` (`TestEvent`). Any other type arrives as `UnknownWebhookEvent`.

Every event has `id`, `type`, `seq`, `created_at` and `data`.

- **Retries and duplicates.** The platform retries a delivery when your endpoint answers non-2xx or
  does not answer. `event.id` is the same across attempts, and `X-Voice-Delivery-Id` is new for
  each attempt. Deduplicate by `event.id`.
- **Order.** Deliveries can arrive out of order. For `call.*` events with `data.call`, `seq` orders
  the events of one call: apply the event only if its `seq` is greater than the last one you stored.
  `seq` is 0 for `call.quality`, `balance.low` and `webhook.test`.
- **Answer fast.** Store the event and answer 200, then do slow work in a queue.
- **Secret rotation.** Rotate the secret in the dashboard. The new secret works immediately. During
  your own switch, pass both: `secret=[new_secret, old_secret]`. A signature matching any of them is
  accepted. Remove the old one when done.

## Testing webhooks

In the dashboard, open Integration and press "Send test event". It sends a `webhook.test` event to
your endpoint.

In unit tests, sign a payload the way the platform does:

```python
from datetime import UTC, datetime

from yolla_voice import WebhookDispatcher, sign_webhook

secret = "whsec_test"
received = []
dispatcher = WebhookDispatcher(secret=secret, on={"webhook.test": received.append})

signed = sign_webhook(
    {
        "id": "evt_1",
        "type": "webhook.test",
        "seq": 0,
        "createdAt": datetime.now(UTC).isoformat(),
        "data": {},
    },
    secret=secret,
)

response = dispatcher.handle(signed.body, signed.headers)
assert response.status == 200
assert received[0].id == "evt_1"
```

With a client, `client.webhooks.sign(payload)` signs with the client secret.

## Requirements

- Python 3.11 or newer. Runtime dependencies: `httpx` and `pydantic` 2.
- The package ships type information (`py.typed`).
- Server-side only. The API key can start calls and spend money: never ship it to a browser or a
  mobile app. Give the app only the `call_token` of a call.

## Versioning

The package follows semantic versioning. While the API contract is a draft, versions are 0.x and a
minor release may include breaking changes. They are listed in [CHANGELOG.md](CHANGELOG.md).

## License

MIT
