from collections.abc import Mapping
from typing import Any, TypeVar
from urllib.parse import quote

from pydantic import BaseModel, ValidationError

from yolla_voice._http.types import HttpResponse
from yolla_voice.errors import YollaVoiceError

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_model(response: HttpResponse[Any], model_type: type[ModelT]) -> ModelT:
    try:
        return model_type.model_validate(response.data)
    except (ValidationError, TypeError, ValueError):
        raise YollaVoiceError(
            "Invalid response payload",
            code="invalid_response",
            status=response.status,
            request_id=_header(response.headers, "X-Request-Id"),
        ) from None


def path_param(value: str) -> str:
    return quote(value, safe="")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered_name:
            return value
    return None
