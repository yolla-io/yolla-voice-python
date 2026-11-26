"""A standalone ASGI webhook endpoint.

Run with YOLLA_WEBHOOK_SECRET set, using any ASGI server, for example:

    uvicorn examples.asgi_webhooks:app

Inside a framework, add `app` as an exact route, such as FastAPI's
`api.add_route("/webhooks/yolla", app, methods=["POST"])` or Starlette's
`Route("/webhooks/yolla", app, methods=["POST"])`.
"""

from yolla_voice import (
    AsyncWebhookDispatcher,
    BalanceEvent,
    CallEvent,
    WebhookEvent,
    WebhookVerificationError,
    create_asgi_app,
)


async def on_call_completed(event: CallEvent) -> None:
    call = event.data.call
    print("completed:", call.id, call.billed_duration, call.end_reason)


def on_balance_low(event: BalanceEvent) -> None:
    print("balance low:", event.data.available.amount)


def on_unhandled(event: WebhookEvent) -> None:
    print("ignored:", event.type)


def on_error(error: Exception) -> None:
    if isinstance(error, WebhookVerificationError):
        print("rejected webhook:", error.reason)
    else:
        print("webhook handler failed:", repr(error))


dispatcher = AsyncWebhookDispatcher(
    on={"call.completed": on_call_completed, "balance.low": on_balance_low},
    on_unhandled=on_unhandled,
    on_error=on_error,
)
app = create_asgi_app(dispatcher)
