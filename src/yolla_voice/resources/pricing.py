from yolla_voice._http.client import AsyncHttpClient, HttpClient
from yolla_voice._http.types import RequestSpec
from yolla_voice.models import NumberPrice

from ._common import parse_model, path_param


class Pricing:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get_number_price(
        self,
        number: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> NumberPrice:
        response = self._http.request(
            RequestSpec(method="GET", path=f"/v1/pricing/numbers/{path_param(number)}"),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, NumberPrice)


class AsyncPricing:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def get_number_price(
        self,
        number: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> NumberPrice:
        response = await self._http.request(
            RequestSpec(method="GET", path=f"/v1/pricing/numbers/{path_param(number)}"),
            timeout=timeout,
            max_retries=max_retries,
        )
        return parse_model(response, NumberPrice)


__all__ = ["AsyncPricing", "Pricing"]
