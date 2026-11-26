from unittest.mock import Mock, call

import pytest

from yolla_voice.models import Call
from yolla_voice.pagination import AsyncCallPage, CallPage, aiter_calls, iter_calls


def make_call(call_id: str) -> Call:
    return Call.model_validate(
        {
            "id": call_id,
            "status": "created",
            "to": "14155550100",
            "from": "14155550199",
            "externalUserId": "user-1",
            "createdAt": "2026-11-25T12:00:00Z",
            "expiresAt": "2026-11-25T13:00:00Z",
        }
    )


def test_single_sync_page_stops_at_null_cursor_and_rejects_next_page():
    first = make_call("call-1")
    fetch_page = Mock()
    page = CallPage(items=[first], next_cursor=None, fetch_page=fetch_page)

    assert page.items == [first]
    assert page.has_next_page is False
    assert list(iter_calls(page)) == [first]
    fetch_page.assert_not_called()
    with pytest.raises(ValueError, match="next cursor"):
        page.next_page()


def test_sync_iterator_is_lazy_yields_in_order_and_fetches_each_cursor_once():
    calls = [make_call(f"call-{number}") for number in range(1, 4)]
    pages: dict[str, CallPage] = {}
    fetch_page = Mock(side_effect=lambda cursor: pages[cursor])
    final_page = CallPage(items=[calls[2]], next_cursor=None, fetch_page=fetch_page)
    second_page = CallPage(items=[calls[1]], next_cursor="cursor-3", fetch_page=fetch_page)
    pages.update({"cursor-2": second_page, "cursor-3": final_page})
    first_page = CallPage(items=[calls[0]], next_cursor="cursor-2", fetch_page=fetch_page)

    assert first_page.has_next_page is True
    iterator = iter_calls(first_page)
    fetch_page.assert_not_called()

    assert list(iterator) == calls
    assert fetch_page.call_args_list == [call("cursor-2"), call("cursor-3")]


async def test_single_async_page_stops_at_null_cursor_and_rejects_next_page():
    first = make_call("call-1")
    fetched_cursors: list[str] = []

    async def fetch_page(cursor: str) -> AsyncCallPage:
        fetched_cursors.append(cursor)
        raise AssertionError("null cursor must not be fetched")

    page = AsyncCallPage(items=[first], next_cursor=None, fetch_page=fetch_page)

    assert page.items == [first]
    assert page.has_next_page is False
    assert [item async for item in aiter_calls(page)] == [first]
    assert fetched_cursors == []
    with pytest.raises(ValueError, match="next cursor"):
        await page.next_page()


async def test_async_iterator_is_lazy_yields_in_order_and_fetches_each_cursor_once():
    calls = [make_call(f"call-{number}") for number in range(1, 4)]
    pages: dict[str, AsyncCallPage] = {}
    fetched_cursors: list[str] = []

    async def fetch_page(cursor: str) -> AsyncCallPage:
        fetched_cursors.append(cursor)
        return pages[cursor]

    final_page = AsyncCallPage(items=[calls[2]], next_cursor=None, fetch_page=fetch_page)
    second_page = AsyncCallPage(items=[calls[1]], next_cursor="cursor-3", fetch_page=fetch_page)
    pages.update({"cursor-2": second_page, "cursor-3": final_page})
    first_page = AsyncCallPage(items=[calls[0]], next_cursor="cursor-2", fetch_page=fetch_page)

    assert first_page.has_next_page is True
    iterator = aiter_calls(first_page)
    assert fetched_cursors == []

    assert [item async for item in iterator] == calls
    assert fetched_cursors == ["cursor-2", "cursor-3"]
