from yolla_voice._http.client import AsyncHttpClient, HttpClient
from yolla_voice._http.types import RequestSpec
from yolla_voice.models import Balance

from ._common import parse_model


class BalanceResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Balance:
        response = self._http.request(
            RequestSpec(method="GET", path="/v1/balance"),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, Balance)


class AsyncBalanceResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def get(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Balance:
        response = await self._http.request(
            RequestSpec(method="GET", path="/v1/balance"),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, Balance)


__all__ = ["AsyncBalanceResource", "BalanceResource"]
