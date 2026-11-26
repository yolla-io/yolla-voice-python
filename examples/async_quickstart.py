"""Create a call and page through completed calls with the asynchronous client.

Run with YOLLA_API_KEY set:

    uv run python examples/async_quickstart.py
"""

import asyncio

from yolla_voice import AsyncYollaVoice, CreateCallRequest


async def main() -> None:
    async with AsyncYollaVoice() as client:
        created = await client.calls.create(
            CreateCallRequest(to="14155550100", external_user_id="user-42"),
        )
        print(created.call.id, created.call.call_token)

        page = await client.calls.list(status="completed", limit=100)
        while True:
            for call in page.items:
                print(call.id, call.billed_duration)
            if not page.has_next_page:
                break
            page = await page.next_page()

        balance = await client.balance.get()
        print("available:", balance.available.amount)


if __name__ == "__main__":
    asyncio.run(main())
