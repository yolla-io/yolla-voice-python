from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    query: Mapping[str, Any] | None = None
    body: Any | None = None
    headers: Mapping[str, str] | None = None
    retryable: bool = True
    # False when a lost response may hide a processed, non-repeatable state change.
    retry_transport_errors: bool = True


@dataclass(frozen=True)
class HttpResponse(Generic[T]):
    data: T
    status: int
    headers: Mapping[str, str]
