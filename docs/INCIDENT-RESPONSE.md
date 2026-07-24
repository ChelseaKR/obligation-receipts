# Incident response

Obligation Receipts is not deployed, but confidential-evidence exposure,
credential exposure, a false pass, or a disabled security gate can still be an
incident.

1. Stop the affected workflow and preserve non-sensitive diagnostic facts.
2. If a credential may be exposed, rotate it, revoke the old value, and inspect
   issuer audit logs before considering repository-history cleanup.
3. If confidential evidence was processed contrary to policy, isolate the
   workspace, stop copying it, identify every storage location, and obtain
   legal/privacy advice before deletion could destroy required evidence.
4. Correct the control and add a regression test.
5. Record confirmed incidents under `docs/incidents/YYYY-MM-DD-<slug>.md` with
   severity, UTC timeline, impact, detection, systemic root cause, actions,
   owners, and due dates.

Never include credentials, confidential contracts, personal data, or raw
evidence in an issue or postmortem.
