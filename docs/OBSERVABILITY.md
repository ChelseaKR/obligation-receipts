# Observability declaration

**Tier:** C — offline CLI/library

Obligation Receipts has no service, network route, background worker,
deployment, or availability objective. OpenTelemetry, RED/USE metrics, health
endpoints, SLOs, and distributed tracing are not applicable to M0.

The CLI's stdout is its canonical machine-readable result channel and stderr is
reserved for bounded human-readable failures. It emits no contract text,
evidence content, credentials, or structured operational logs. Any future
logging mode must keep sensitive values out of logs and add explicit redaction
tests before confidential evidence is allowed.
