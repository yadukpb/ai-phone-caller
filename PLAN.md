# Improvement plan

## Completed in this pass

1. Add optional API-key authentication so the control plane is not accidentally public.
2. Make call records durable and queryable with JSON metadata rather than Python repr strings.
3. Add list and explicit status endpoints for operators and webhooks.
4. Return the correct HTTP status when a provider call fails.
5. Restrict voice-reference paths to a configured voice directory.
6. Avoid loading both Qwen models at once; use one-model GPU caching with configurable fallback.
7. Add structured health checks and a dependency-free smoke-check script.

## Remaining infrastructure phase

1. Replace SQLite with PostgreSQL and move campaign dispatch to a durable queue.
2. Consume LiveKit participant/disconnect events to update call status automatically.
3. Add encrypted recordings, transcript retention policies, and observability.
4. Load-test Qwen generation and tune sentence chunking for phone latency.

The application-level campaign, contact, opt-out, rate-limit, transcript, recording, and pause/run features are implemented in the current SQLite-backed version.

The application remains dry-run by default. A live carrier call occurs only when `DRY_RUN=false`, LiveKit credentials are present, and a SIP trunk is configured.
