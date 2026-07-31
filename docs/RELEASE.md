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

Public or package-registry publication remains blocked until all of these exist:

- initialized version control and a hosted private repository;
- protected main and tag rulesets with required checks;
- an independently reviewed release decision;
- signed tags and verified maintainer identity;
- SBOM and a distributable artifact signature (candidate build provenance is
  now issued);
- private vulnerability reporting and incident labels;
- exact package URLs and security contact route; and
- discovery evidence supporting continued product development.

The candidate workflow intentionally has no contents-write permission, publish
job, or registry credential.
