# Changelog

## 0.2.0 - 2026-11-27

- Added the `call.billed` webhook event, delivered as a `CallEvent` once per call after `call.completed`
  with the final `price` and `billed_duration`.
- Refreshed the contract snapshot and generated models.

## 0.1.0

Initial release.

- Synchronous `YollaVoice` and asynchronous `AsyncYollaVoice` clients for calls, balance, and number
  pricing, configured by arguments or `YOLLA_API_KEY` and `YOLLA_WEBHOOK_SECRET`.
- Typed Pydantic models generated from the Reseller API contract, with snake_case attributes,
  camelCase wire aliases, and forward-compatible unknown fields and enum values.
- Lazy cursor pagination with `calls.list` pages and `calls.iter_all`.
- Retries with full-jitter exponential backoff and `Retry-After`, per-attempt timeouts in seconds,
  and automatic idempotency keys for `calls.create`.
- Typed errors carrying `status`, `code`, and `request_id`.
- Webhook verification and signing with secret rotation, known and unknown event models, sync and
  async dispatchers, and ASGI and WSGI endpoints.
