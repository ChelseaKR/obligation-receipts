# Release posture

Obligation Receipts is an unreleased technical alpha. Local wheels and source
archives are test artifacts, not publication.

The committed CI workflow verifies code, the synthetic replay, packaging,
runtime dependency exposure, secrets, SAST, and workflow safety. A `v*` tag
builds and uploads a release candidate only when the tag matches the package
version.

Public or package-registry publication remains blocked until all of these exist:

- initialized version control and a hosted private repository;
- protected main and tag rulesets with required checks;
- an independently reviewed release decision;
- signed tags and verified maintainer identity;
- SBOM, artifact signature, and provenance;
- private vulnerability reporting and incident labels;
- exact package URLs and security contact route; and
- discovery evidence supporting continued product development.

The candidate workflow intentionally has no publish permission or registry
credential.
