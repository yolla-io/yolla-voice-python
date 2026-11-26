"""A standalone WSGI webhook endpoint.

Run with YOLLA_WEBHOOK_SECRET set:

    uv run python examples/wsgi_webhooks.py

In production, serve `app` with any WSGI server, for example `gunicorn examples.wsgi_webhooks:app`,
or mount it under a path with Werkzeug's `DispatcherMiddleware`.
"""

from wsgiref.simple_server import make_server

from yolla_voice import CallEvent, WebhookDispatcher, WebhookVerificationError, create_wsgi_app


def on_call_event(event: CallEvent) -> None:
    print(event.type, event.data.call.id, "seq:", event.seq)


def on_error(error: Exception) -> None:
    if isinstance(error, WebhookVerificationError):
        print("rejected webhook:", error.reason)
    else:
        print("webhook handler failed:", repr(error))


dispatcher = WebhookDispatcher(
    on={
        "call.answered": on_call_event,
        "call.completed": on_call_event,
        "call.expired": on_call_event,
    },
    on_error=on_error,
)
app = create_wsgi_app(dispatcher)


def main() -> None:
    with make_server("127.0.0.1", 8000, app) as server:
        print("Listening on http://127.0.0.1:8000")
        server.serve_forever()


if __name__ == "__main__":
    main()
