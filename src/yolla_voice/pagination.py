from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

from .models import Call

__all__ = ["AsyncCallPage", "CallPage", "aiter_calls", "iter_calls"]


class CallPage:
    def __init__(
        self,
        items: list[Call],
        next_cursor: str | None,
        fetch_page: Callable[[str], CallPage],
    ) -> None:
        self.items = items
        self.next_cursor = next_cursor
        self._fetch_page = fetch_page

    @property
    def has_next_page(self) -> bool:
        return self.next_cursor is not None

    def next_page(self) -> CallPage:
        if self.next_cursor is None:
            raise ValueError("Cannot fetch the next page without a next cursor")
        return self._fetch_page(self.next_cursor)


class AsyncCallPage:
    def __init__(
        self,
        items: list[Call],
        next_cursor: str | None,
        fetch_page: Callable[[str], Awaitable[AsyncCallPage]],
    ) -> None:
        self.items = items
        self.next_cursor = next_cursor
        self._fetch_page = fetch_page

    @property
    def has_next_page(self) -> bool:
        return self.next_cursor is not None

    async def next_page(self) -> AsyncCallPage:
        if self.next_cursor is None:
            raise ValueError("Cannot fetch the next page without a next cursor")
        return await self._fetch_page(self.next_cursor)


def iter_calls(first_page: CallPage) -> Iterator[Call]:
    page = first_page
    while True:
        yield from page.items
        if not page.has_next_page:
            return
        page = page.next_page()


async def aiter_calls(first_page: AsyncCallPage) -> AsyncIterator[Call]:
    page = first_page
    while True:
        for item in page.items:
            yield item
        if not page.has_next_page:
            return
        page = await page.next_page()
