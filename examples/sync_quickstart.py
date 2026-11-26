"""Create a call, read it back, and list recent calls with the synchronous client.

Run with YOLLA_API_KEY set:

    uv run python examples/sync_quickstart.py
"""

from yolla_voice import (
    ConflictError,
    CreateCallRequest,
    PermissionError,
    YollaVoice,
    YollaVoiceError,
)


def main() -> None:
    with YollaVoice() as client:
        try:
            created = client.calls.create(
                CreateCallRequest(to="14155550100", external_user_id="user-42"),
                idempotency_key="order-A-1001",
            )
        except PermissionError as error:
            print("Destination or caller id is not allowed:", error.code)
            return
        except ConflictError as error:
            print("Idempotency key reused with different parameters:", error.code)
            return
        except YollaVoiceError as error:
            print("Request failed:", error.status, error.code, error.request_id)
            return

        call = created.call
        # Give call.call_token to your app. The app uses it to start the call.
        print(call.id, call.call_token, call.expires_at, "replayed:", created.replayed)

        print("status:", client.calls.get(call.id).status)

        for recent in client.calls.iter_all(external_user_id="user-42", limit=50):
            print(recent.id, recent.status, recent.duration)

        balance = client.balance.get()
        print("available:", balance.available.amount, balance.available.currency)

        price = client.pricing.get_number_price("14155550100")
        print("per minute:", price.rate.per_minute.amount, price.rate.per_minute.currency)


if __name__ == "__main__":
    main()
