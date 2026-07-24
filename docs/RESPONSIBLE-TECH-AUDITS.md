# Responsible-technology audit

**Date:** 2026-07-22
**Scope:** M0 offline technical alpha

## Ethics

The tool could improve buyer leverage and make vague vendor promises visible. It
could also become a mechanism for false certainty, adversarial contract
administration, or withholding payment based on weak proxy tests. M0 therefore
keeps official acceptance outside the product and preserves ambiguity.

## Bias and accessibility

Automated criteria can systematically privilege what is cheap to measure.
Accessibility is the synthetic example specifically to show that automated scan
results and named human workflow review are different evidence classes.

No user interface exists. Any future HTML review surface activates WCAG 2.2 AA
automation plus disabled-user/manual review requirements.

## Privacy

Evidence can contain confidential contract, security, operational, or personal
information. M0:

- reads local caller-controlled files;
- emits no evidence content;
- performs no network calls;
- stores no central copy;
- bounds JSON artifacts to 2 MiB; and
- emits content hashes and identifiers that may still be sensitive.

Operators must use a minimally scoped evidence root. Public receipts may require
redacted identifiers or a private/public envelope design in M1.

## Transparency

Every output declares technical scope, unsigned status, and untrusted time.
Documentation lists what the receipt proves and does not prove. `unverifiable`
is a first-class result.

## Security

The primary M0 risks are parser abuse, path traversal, malicious artifacts,
attestation reuse, and result overstatement. Current controls and residual risks
are in the threat model. JSON bytes, nesting, and node counts are bounded;
authenticated reviewer identity remains open.

## Accountability

M0 records supplied owner, reviewer, and issuer names but authenticates none of
them. It cannot provide segregation of duties. Production use is blocked until
governed roles and cryptographic authorization are designed and independently
reviewed.
