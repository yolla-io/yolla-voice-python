import os
from collections.abc import Sequence

WebhookSecret = str | Sequence[str]


def resolve_webhook_secret(secret: WebhookSecret | None) -> tuple[str, ...]:
    if secret is None:
        environment = os.environ.get("YOLLA_WEBHOOK_SECRET")
        if not environment:
            raise ValueError("Missing webhook secret: pass secret or set YOLLA_WEBHOOK_SECRET")
        return (environment,)

    given: Sequence[str] = (secret,) if isinstance(secret, str) else secret
    if not given or (len(given) == 1 and given[0] == ""):
        raise ValueError("Webhook secret must be a non-empty string or a sequence of them")
    if any(not isinstance(item, str) or not item for item in given):
        raise TypeError("Webhook secret must be a non-empty string or a sequence of them")
    return tuple(given)
