# Release posture

Obligation Receipts is an unreleased technical alpha. Local wheels and source
archives are test artifacts, not publication.

The committed CI workflow verifies code, the synthetic replay, packaging,
runtime dependency exposure, secrets, SAST, and workflow safety. A maintainer
may manually select an existing signed stable SemVer tag. The release-candidate
workflow accepts it only when the tag is an annotated SSH-signed tag whose
commit is on and still equals protected `main`; it then checks out that exact
commit, re-runs the gates, builds the candidate, records checksums, and issues
GitHub build provenance before uploading the candidate artifact.

Public or package-registry publication remains blocked until all of these
exist. In place:

- initialized version control and a hosted public repository (`gh repo view
  --json isPrivate` returns false);
- protected main and tag rulesets with required checks (`protect-tags`
  additionally requires signed, immutable tags — deletion and rewrite of a
  matching ref are rejected by GitHub, not just by CI);
- SBOM and a distributable artifact signature (build provenance attestation
  and a keyless cosign signature over `dist/SHA256SUMS` are both issued per
  candidate);
- incident labels (`security`, `incident`); and
- a security contact route: private vulnerability reporting is enabled, so the
  repository Security tab accepts a private advisory. It is confirmable rather
  than asserted — `GET /repos/ChelseaKR/obligation-receipts/private-vulnerability-reporting`
  returns `{"enabled": true}`. See `SECURITY.md`.

Still required:

- an independently reviewed release decision — a second maintainer or outside
  reviewer signing off on cutting a specific version, distinct from the
  automated `verify`/`authorize` gates;
- signed tags and verified maintainer identity — SSH tag signing is
  configured and `.github/allowed_signers` matches the release-signing key,
  but no tag has been cut yet, and that key still needs to be added under the
  maintainer's GitHub account as a *signing* key (github.com/settings/keys)
  so pushed tags carry GitHub's own Verified badge, not only CI-internal
  verification;
- exact package URLs — resolve once a package is actually published to a
  registry; SECURITY.md commits in advance to the README/release notes as the
  only canonical source; and
- discovery evidence supporting continued product development — the sample
  pack is unrated candidate selection only (see
  `docs/discovery/public-sample-candidates.md`); needs a selection owner and
  two independent raters to actually complete it.

The candidate workflow intentionally has no contents-write permission, publish
job, or registry credential.
