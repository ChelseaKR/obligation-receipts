# Security policy

Obligation Receipts is an unreleased technical alpha. Do not use it as the sole
basis for contractual acceptance, payment, compliance, or production-security
decisions.

Report vulnerabilities privately to the repository owner. Do not include real
contracts, credentials, personal information, or confidential evidence in a
report.

The M0 parser accepts only local TOML and bounded JSON. Any code path that
executes a manifest-supplied command, fetches a manifest-supplied URL, permits an
artifact path to escape its root, or emits raw evidence content is a security
defect.

Source and evidence paths use portable relative syntax. Windows drives/UNC,
backslashes, colon/URI forms, traversal, dot, and empty segments are rejected
before root access. Contract-source hashing is capped at 16 MiB; manifests,
JSON artifacts, plans, and receipts are capped at 2 MiB. Special files are
opened nonblocking and rejected unless `fstat` identifies a regular file.

Evidence evaluation must parse and hash the same byte snapshot. Receipt
verification must reject ambiguous JSON and internally inconsistent closed
payloads, even if their checksum was recomputed.

Attestations bind the exact evidence ID as well as contract, version, manifest,
and obligation. M0 does not authenticate the reviewer/issuer or establish a
validity window.

Evidence plans are sensitive operational artifacts. The default profile redacts
filesystem paths, source locators, and free-text reasons, but declared assertion
thresholds and binding identifiers still require a disclosure review. The
local-sensitive profile must not be published casually.

Single-evidence check digests are content identifiers, not authentication, and
may correlate confidential artifacts. Use a minimally scoped, trusted
evidence-root filesystem and apply explicit retention/access controls to stdout,
CI logs, and retained diagnostics.
