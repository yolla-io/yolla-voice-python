import platform
from asyncio import sleep as async_sleep
from dataclasses import dataclass, field
from math import isfinite
from random import random
from time import sleep
from typing import Any

import httpx

from yolla_voice import __version__
from yolla_voice._http.common import decode_body, retry_delay
from yolla_voice._http.types import HttpResponse, RequestSpec
from yolla_voice.errors import (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    YollaVoiceError,
    error_from_response,
)


@dataclass
class HttpConfig:
    api_key: str = field(repr=False)
    base_url: str
    timeout: float = 30.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.timeout = _validate_timeout(self.timeout)
        self.max_retries = _validate_max_retries(self.max_retries)


def _validate_timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timeout must be a finite positive number")
    timeout = float(value)
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number")
    return timeout


def _validate_max_retries(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("max_retries must be a nonnegative integer")
    if value < 0:
        raise ValueError("max_retries must be a nonnegative integer")
    return value


def _request_options(
    config: HttpConfig,
    timeout: float | None,
    max_retries: int | None,
) -> tuple[float, int]:
    return (
        config.timeout if timeout is None else _validate_timeout(timeout),
        config.max_retries if max_retries is None else _validate_max_retries(max_retries),
    )


def _url(config: HttpConfig, spec: RequestSpec) -> str:
    return f"{config.base_url}/{spec.path.lstrip('/')}"


def _headers(config: HttpConfig, spec: RequestSpec) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Accept": "application/json",
        "User-Agent": f"yolla-voice-python/{__version__} Python/{platform.python_version()}",
    }
    if spec.body is not None:
        headers["Content-Type"] = "application/json"
    if spec.headers is not None:
        headers.update(spec.headers)
    return headers


def _successful_response(response: httpx.Response) -> HttpResponse[Any]:
    return HttpResponse(
        data=decode_body(response.status_code, response.headers, response.content),
        status=response.status_code,
        headers=response.headers,
    )


def _response_error(response: httpx.Response) -> YollaVoiceError:
    body = decode_body(response.status_code, response.headers, response.content)
    return error_from_response(response.status_code, body, response.headers)


def _can_retry(spec: RequestSpec, attempt: int, max_retries: int) -> bool:
    return spec.retryable and attempt < max_retries


def _can_retry_transport_error(spec: RequestSpec, attempt: int, max_retries: int) -> bool:
    return spec.retry_transport_errors and _can_retry(spec, attempt, max_retries)


def _can_retry_response(spec: RequestSpec, attempt: int, max_retries: int, status: int) -> bool:
    return _can_retry(spec, attempt, max_retries) and (status == 429 or 500 <= status <= 599)


def _response_retry_delay(attempt: int, error: YollaVoiceError) -> float:
    retry_after = error.retry_after if isinstance(error, RateLimitError) else None
    return retry_delay(attempt, retry_after, random())


def _connection_retry_delay(attempt: int) -> float:
    return retry_delay(attempt, None, random())


def _connection_error(error: httpx.TransportError) -> APIConnectionError:
    if isinstance(error, httpx.TimeoutException):
        return APITimeoutError()
    return APIConnectionError()


class HttpClient:
    def __init__(
        self,
        config: HttpConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._client = httpx.Client(transport=transport, follow_redirects=False)
        self._closed = False

    def request(
        self,
        spec: RequestSpec,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> HttpResponse[Any]:
        if self._closed:
            raise RuntimeError("HTTP client is closed")
        request_timeout, retries = _request_options(self._config, timeout, max_retries)

        for attempt in range(retries + 1):
            try:
                response = self._client.request(
                    spec.method,
                    _url(self._config, spec),
                    params=spec.query,
                    json=spec.body,
                    headers=_headers(self._config, spec),
                    timeout=request_timeout,
                )
            except httpx.TransportError as error:
                if not _can_retry_transport_error(spec, attempt, retries):
                    raise _connection_error(error) from error
                sleep(_connection_retry_delay(attempt))
                continue

            if 200 <= response.status_code < 300:
                return _successful_response(response)

            response_error = _response_error(response)
            if not _can_retry_response(spec, attempt, retries, response.status_code):
                raise response_error
            sleep(_response_retry_delay(attempt, response_error))

        raise RuntimeError("unreachable")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._client.close()


class AsyncHttpClient:
    def __init__(
        self,
        config: HttpConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        self._closed = False

    async def request(
        self,
        spec: RequestSpec,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> HttpResponse[Any]:
        if self._closed:
            raise RuntimeError("HTTP client is closed")
        request_timeout, retries = _request_options(self._config, timeout, max_retries)

        for attempt in range(retries + 1):
            try:
                response = await self._client.request(
                    spec.method,
                    _url(self._config, spec),
                    params=spec.query,
                    json=spec.body,
                    headers=_headers(self._config, spec),
                    timeout=request_timeout,
                )
            except httpx.TransportError as error:
                if not _can_retry_transport_error(spec, attempt, retries):
                    raise _connection_error(error) from error
                await async_sleep(_connection_retry_delay(attempt))
                continue

            if 200 <= response.status_code < 300:
                return _successful_response(response)

            response_error = _response_error(response)
            if not _can_retry_response(spec, attempt, retries, response.status_code):
                raise response_error
            await async_sleep(_response_retry_delay(attempt, response_error))

        raise RuntimeError("unreachable")

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()


__all__ = ["AsyncHttpClient", "HttpClient", "HttpConfig"]
