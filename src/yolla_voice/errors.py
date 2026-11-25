from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any, Literal


class YollaVoiceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        status: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.request_id = request_id


class ValidationError(YollaVoiceError):
    pass


class AuthenticationError(YollaVoiceError):
    pass


class InsufficientBalanceError(YollaVoiceError):
    pass


class PermissionError(YollaVoiceError):
    pass


class NotFoundError(YollaVoiceError):
    pass


class ConflictError(YollaVoiceError):
    pass


class RateLimitError(YollaVoiceError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        status: int | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, code=code, status=status, request_id=request_id)
        self.retry_after = retry_after


class ServerError(YollaVoiceError):
    pass


class APIConnectionError(YollaVoiceError):
    _error_code = "connection_error"

    def __init__(
        self,
        message: str = "Connection failed",
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, code=self._error_code, request_id=request_id)


class APITimeoutError(APIConnectionError):
    _error_code = "timeout"

    def __init__(
        self,
        message: str = "Request timed out",
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, request_id=request_id)


class WebhookVerificationError(YollaVoiceError):
    def __init__(
        self,
        message: str = "Webhook verification failed",
        *,
        reason: Literal["missing_header", "bad_signature", "stale_timestamp", "invalid_payload"],
    ) -> None:
        super().__init__(message, code="webhook_verification_error")
        self.reason = reason


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered_name:
            return value
    return None


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return max(0.0, seconds) if isfinite(seconds) else None

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    return max(0.0, (retry_at - now).total_seconds())


def error_from_response(
    status: int,
    body: Any,
    headers: Mapping[str, str],
) -> YollaVoiceError:
    code = "unknown_error"
    message = f"HTTP {status}"
    request_id = _header(headers, "X-Request-Id")

    if isinstance(body, Mapping):
        error_body = body.get("error")
        if isinstance(error_body, Mapping):
            body_code = error_body.get("code")
            body_message = error_body.get("message")
            body_request_id = error_body.get("requestId")
            if isinstance(body_code, str) and isinstance(body_message, str):
                code = body_code
                message = body_message
            if isinstance(body_request_id, str):
                request_id = body_request_id

    error_type: type[YollaVoiceError]
    if status in (400, 422):
        error_type = ValidationError
    elif status == 401:
        error_type = AuthenticationError
    elif status == 402:
        error_type = InsufficientBalanceError
    elif status == 403:
        error_type = PermissionError
    elif status == 404:
        error_type = NotFoundError
    elif status == 409:
        error_type = ConflictError
    elif status == 429:
        return RateLimitError(
            message,
            code=code,
            status=status,
            request_id=request_id,
            retry_after=parse_retry_after(_header(headers, "Retry-After")),
        )
    elif 500 <= status <= 599:
        error_type = ServerError
    else:
        error_type = YollaVoiceError

    return error_type(message, code=code, status=status, request_id=request_id)


__all__ = [
    "APIConnectionError",
    "APITimeoutError",
    "AuthenticationError",
    "ConflictError",
    "InsufficientBalanceError",
    "NotFoundError",
    "PermissionError",
    "RateLimitError",
    "ServerError",
    "ValidationError",
    "WebhookVerificationError",
    "YollaVoiceError",
    "error_from_response",
    "parse_retry_after",
]
