from collections.abc import Mapping

TIMESTAMP_HEADER = "X-Voice-Timestamp"
SIGNATURE_HEADER = "X-Voice-Signature"
DELIVERY_ID_HEADER = "X-Voice-Delivery-Id"


def get_header(headers: Mapping[str, str], name: str) -> str | None:
    lowered_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered_name:
            return value
    return None
