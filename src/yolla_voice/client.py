import os
from collections.abc import Sequence
from types import TracebackType
from typing import Self

import httpx

from ._http.client import AsyncHttpClient, HttpClient, HttpConfig
from .resources.balance import AsyncBalanceResource, BalanceResource
from .resources.calls import AsyncCalls, Calls
from .resources.pricing import AsyncPricing, Pricing
from .webhooks import Webhooks

DEFAULT_BASE_URL = "https://platform.yolla.io/api"


def _required_option(explicit: str | None, option: str, environment: str) -> str:
    value = explicit if explicit is not None else os.environ.get(environment)
    if not value:
        raise ValueError(f"{option} is required; pass {option} or set {environment}")
    return value


def _webhook_secret(value: str | Sequence[str] | None) -> str | Sequence[str] | None:
    return value if value is not None else os.environ.get("YOLLA_WEBHOOK_SECRET")


class YollaVoice:
    def __init__(
        self,
        api_key: str | None = None,
        webhook_secret: str | Sequence[str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_api_key = _required_option(api_key, "api_key", "YOLLA_API_KEY")
        self._webhook_secret = _webhook_secret(webhook_secret)
        self._timeout = timeout
        self._max_retries = max_retries
        self._http = HttpClient(
            HttpConfig(
                api_key=resolved_api_key,
                base_url=DEFAULT_BASE_URL,
                timeout=timeout,
                max_retries=max_retries,
            ),
            transport=transport,
        )
        self.calls = Calls(self._http)
        self.balance = BalanceResource(self._http)
        self.pricing = Pricing(self._http)
        self.webhooks = Webhooks(self._webhook_secret)

    def __repr__(self) -> str:
        return f"YollaVoice(timeout={self._timeout!r}, max_retries={self._max_retries!r})"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class AsyncYollaVoice:
    def __init__(
        self,
        api_key: str | None = None,
        webhook_secret: str | Sequence[str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        resolved_api_key = _required_option(api_key, "api_key", "YOLLA_API_KEY")
        self._webhook_secret = _webhook_secret(webhook_secret)
        self._timeout = timeout
        self._max_retries = max_retries
        self._http = AsyncHttpClient(
            HttpConfig(
                api_key=resolved_api_key,
                base_url=DEFAULT_BASE_URL,
                timeout=timeout,
                max_retries=max_retries,
            ),
            transport=transport,
        )
        self.calls = AsyncCalls(self._http)
        self.balance = AsyncBalanceResource(self._http)
        self.pricing = AsyncPricing(self._http)
        self.webhooks = Webhooks(self._webhook_secret)

    def __repr__(self) -> str:
        return f"AsyncYollaVoice(timeout={self._timeout!r}, max_retries={self._max_retries!r})"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


__all__ = ["DEFAULT_BASE_URL", "AsyncYollaVoice", "YollaVoice"]
