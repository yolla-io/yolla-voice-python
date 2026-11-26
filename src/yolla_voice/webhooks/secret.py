import os
from collections.abc import Sequence

WebhookSecret = str | Sequence[str]


def resolve_webhook_secret(secret: WebhookSecret | None) -> tuple[str, ...]:
    if secret is None:
        given: Sequence[str] = ()
    elif isinstance(secret, str):
        given = (secret,)
    else:
        given = secret

    if not given or (len(given) == 1 and given[0] == ""):
        environment = os.environ.get("YOLLA_WEBHOOK_SECRET")
        if not environment:
            raise ValueError("Missing webhook secret: pass secret or set YOLLA_WEBHOOK_SECRET")
        return (environment,)

    if any(not isinstance(item, str) or not item for item in given):
        raise TypeError("Webhook secret must be a non-empty string or a sequence of them")
    return tuple(given)
