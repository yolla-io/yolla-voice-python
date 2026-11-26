from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from yolla_voice._http.client import AsyncHttpClient, HttpClient
from yolla_voice._http.types import RequestSpec
from yolla_voice.models import Call, CallList, CallStatus, CreateCallRequest, CreateCallResponse
from yolla_voice.pagination import AsyncCallPage, CallPage, aiter_calls, iter_calls

from ._common import parse_model, path_param


@dataclass(frozen=True)
class CreateCallResult:
    call: CreateCallResponse
    replayed: bool


def _query(
    *,
    status: CallStatus | str | None,
    external_user_id: str | None,
    from_: datetime | str | None,
    to: datetime | str | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    values = {
        "status": str(status) if status is not None else None,
        "externalUserId": external_user_id,
        "from": from_.isoformat() if isinstance(from_, datetime) else from_,
        "to": to.isoformat() if isinstance(to, datetime) else to,
        "limit": limit,
        "cursor": cursor,
    }
    return {key: value for key, value in values.items() if value is not None}


def _idempotency_key(value: str | None) -> str:
    key = str(uuid4()) if value is None else value
    if len(key) > 128:
        raise ValueError("idempotency_key must not exceed 128 characters")
    return key


class Calls:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        request: CreateCallRequest,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> CreateCallResult:
        key = _idempotency_key(idempotency_key)
        response = self._http.request(
            RequestSpec(
                method="POST",
                path="/v1/calls",
                body=request.model_dump(by_alias=True, exclude_unset=True),
                headers={"Idempotency-Key": key},
            ),
            timeout=timeout,
            max_retries=max_retries,
        )
        return CreateCallResult(
            call=parse_model(response, CreateCallResponse),
            replayed=response.status == 200,
        )

    def list(
        self,
        *,
        status: CallStatus | str | None = None,
        external_user_id: str | None = None,
        from_: datetime | str | None = None,
        to: datetime | str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> CallPage:
        response = self._http.request(
            RequestSpec(
                method="GET",
                path="/v1/calls",
                query=_query(
                    status=status,
                    external_user_id=external_user_id,
                    from_=from_,
                    to=to,
                    limit=limit,
                    cursor=cursor,
                ),
            ),
            timeout=timeout,
            max_retries=max_retries,
        )
        data = parse_model(response, CallList)

        def fetch_page(next_cursor: str) -> CallPage:
            return self.list(
                status=status,
                external_user_id=external_user_id,
                from_=from_,
                to=to,
                limit=limit,
                cursor=next_cursor,
                timeout=timeout,
                max_retries=max_retries,
            )

        return CallPage(data.items, data.next_cursor, fetch_page)

    def iter_all(
        self,
        *,
        status: CallStatus | str | None = None,
        external_user_id: str | None = None,
        from_: datetime | str | None = None,
        to: datetime | str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Iterator[Call]:
        first_page = self.list(
            status=status,
            external_user_id=external_user_id,
            from_=from_,
            to=to,
            limit=limit,
            cursor=cursor,
            timeout=timeout,
            max_retries=max_retries,
        )
        yield from iter_calls(first_page)

    def get(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        response = self._http.request(
            RequestSpec(method="GET", path=f"/v1/calls/{path_param(call_id)}"),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, Call)

    def end(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        return self._action(call_id, "end", timeout=timeout, max_retries=max_retries)

    def hold(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        return self._action(call_id, "hold", timeout=timeout, max_retries=max_retries)

    def unhold(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        return self._action(call_id, "unhold", timeout=timeout, max_retries=max_retries)

    def _action(
        self,
        call_id: str,
        action: str,
        *,
        timeout: float | None,
        max_retries: int | None,
    ) -> Call:
        response = self._http.request(
            RequestSpec(
                method="POST",
                path=f"/v1/calls/{path_param(call_id)}/{action}",
            ),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, Call)


class AsyncCalls:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
        self,
        request: CreateCallRequest,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> CreateCallResult:
        key = _idempotency_key(idempotency_key)
        response = await self._http.request(
            RequestSpec(
                method="POST",
                path="/v1/calls",
                body=request.model_dump(by_alias=True, exclude_unset=True),
                headers={"Idempotency-Key": key},
            ),
            timeout=timeout,
            max_retries=max_retries,
        )
        return CreateCallResult(
            call=parse_model(response, CreateCallResponse),
            replayed=response.status == 200,
        )

    async def list(
        self,
        *,
        status: CallStatus | str | None = None,
        external_user_id: str | None = None,
        from_: datetime | str | None = None,
        to: datetime | str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> AsyncCallPage:
        response = await self._http.request(
            RequestSpec(
                method="GET",
                path="/v1/calls",
                query=_query(
                    status=status,
                    external_user_id=external_user_id,
                    from_=from_,
                    to=to,
                    limit=limit,
                    cursor=cursor,
                ),
            ),
            timeout=timeout,
            max_retries=max_retries,
        )
        data = parse_model(response, CallList)

        async def fetch_page(next_cursor: str) -> AsyncCallPage:
            return await self.list(
                status=status,
                external_user_id=external_user_id,
                from_=from_,
                to=to,
                limit=limit,
                cursor=next_cursor,
                timeout=timeout,
                max_retries=max_retries,
            )

        return AsyncCallPage(data.items, data.next_cursor, fetch_page)

    async def iter_all(
        self,
        *,
        status: CallStatus | str | None = None,
        external_user_id: str | None = None,
        from_: datetime | str | None = None,
        to: datetime | str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> AsyncIterator[Call]:
        first_page = await self.list(
            status=status,
            external_user_id=external_user_id,
            from_=from_,
            to=to,
            limit=limit,
            cursor=cursor,
            timeout=timeout,
            max_retries=max_retries,
        )
        async for call in aiter_calls(first_page):
            yield call

    async def get(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        response = await self._http.request(
            RequestSpec(method="GET", path=f"/v1/calls/{path_param(call_id)}"),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, Call)

    async def end(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        return await self._action(call_id, "end", timeout=timeout, max_retries=max_retries)

    async def hold(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        return await self._action(call_id, "hold", timeout=timeout, max_retries=max_retries)

    async def unhold(
        self,
        call_id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Call:
        return await self._action(call_id, "unhold", timeout=timeout, max_retries=max_retries)

    async def _action(
        self,
        call_id: str,
        action: str,
        *,
        timeout: float | None,
        max_retries: int | None,
    ) -> Call:
        response = await self._http.request(
            RequestSpec(
                method="POST",
                path=f"/v1/calls/{path_param(call_id)}/{action}",
            ),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, Call)


__all__ = ["AsyncCalls", "Calls", "CreateCallResult"]
