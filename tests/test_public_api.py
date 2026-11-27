import inspect

import yolla_voice
from yolla_voice import AsyncYollaVoice, YollaVoice
from yolla_voice.resources.calls import AsyncCalls, Calls
from yolla_voice.webhooks import AsyncWebhookDispatcher, WebhookDispatcher

CLIENT_PARAMETERS = [
    "api_key",
    "webhook_secret",
    "timeout",
    "max_retries",
    "transport",
]
CALL_METHODS = ["create", "list", "iter_all", "get", "end", "hold", "unhold"]
REQUIRED_EXPORTS = {
    "YollaVoice",
    "AsyncYollaVoice",
    "CreateCallRequest",
    "CreateCallResult",
    "CallPage",
    "AsyncCallPage",
    "YollaVoiceError",
    "ValidationError",
    "AuthenticationError",
    "InsufficientBalanceError",
    "PermissionError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
    "APIConnectionError",
    "APITimeoutError",
    "WebhookVerificationError",
    "verify_webhook",
    "sign_webhook",
    "WebhookDispatcher",
    "AsyncWebhookDispatcher",
    "create_asgi_app",
    "create_wsgi_app",
    "UnknownWebhookEvent",
    "__version__",
}


def test_required_names_are_exported_from_the_package_root():
    assert REQUIRED_EXPORTS <= set(yolla_voice.__all__)


def test_version_is_0_1_0():
    assert yolla_voice.__version__ == "0.2.0"


def test_client_constructors_have_identical_parameters_and_defaults():
    for client_type in (YollaVoice, AsyncYollaVoice):
        parameters = inspect.signature(client_type).parameters
        assert list(parameters) == CLIENT_PARAMETERS
        assert parameters["timeout"].default == 30.0
        assert parameters["max_retries"].default == 2


def test_call_resources_expose_matching_sync_and_async_methods():
    for name in CALL_METHODS:
        sync_method = getattr(Calls, name)
        async_method = getattr(AsyncCalls, name)
        assert list(inspect.signature(sync_method).parameters) == list(
            inspect.signature(async_method).parameters
        )
        if name == "iter_all":
            assert inspect.isasyncgenfunction(async_method)
        else:
            assert inspect.iscoroutinefunction(async_method)


def test_per_request_options_are_keyword_only():
    for resource in (Calls, AsyncCalls):
        for name in CALL_METHODS:
            parameters = inspect.signature(getattr(resource, name)).parameters
            for option in ("timeout", "max_retries"):
                assert parameters[option].kind is inspect.Parameter.KEYWORD_ONLY


def test_dispatchers_accept_the_same_options():
    sync_parameters = inspect.signature(WebhookDispatcher).parameters
    async_parameters = inspect.signature(AsyncWebhookDispatcher).parameters
    assert list(sync_parameters) == list(async_parameters)
    assert list(sync_parameters) == ["secret", "tolerance", "on", "on_unhandled", "on_error"]
