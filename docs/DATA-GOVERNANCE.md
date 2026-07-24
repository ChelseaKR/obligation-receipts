# Data governance

## Current permitted data

M0 permits only invented synthetic contract text, manifests, test summaries,
and attestations. Public SOW metadata may be recorded for discovery, but no
confidential contract or evidence artifact may be committed.

Receipts contain bounded results and artifact digests, not source clauses,
screenshots, reports, or evidence content. Generated receipts are disposable
local artifacts and ignored by version control.

## Production gate

Before any confidential contract or production evidence is processed, an
accepted design must define:

- authority and data classification;
- encryption at rest and key handling;
- an ephemeral bounded workspace;
- segregation of manifest approval and evidence review;
- retention and verified deletion;
- backup prohibition or encrypted backup policy;
- incident and breach-response ownership; and
- whether filenames, clause IDs, low counts, or digests create residual
  disclosure risk.

Until then, confidential contracts, credentials, personal information, and
production-security evidence are prohibited.
