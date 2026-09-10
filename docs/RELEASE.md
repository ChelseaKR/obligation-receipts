# Release posture

Obligation Receipts has published nothing. No GitHub release exists, no version
is on PyPI, and local wheels and source archives are test artifacts rather than
publication. What changed on 2026-09-06 is that the machinery to publish now
exists and is reviewable; whether to use it is a separate decision, recorded
below.

## What the workflow does

The committed CI workflow verifies code, the synthetic replay, packaging,
runtime dependency exposure, secrets, SAST, and workflow safety.

A maintainer cuts a signed annotated tag and dispatches `release.yml` from
`main` with that tag as an input:

```
git tag -s vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z
gh workflow run release.yml --ref main -f tag=vX.Y.Z
```

`workflow_dispatch` rather than a tag-push trigger is the point: a tag-push
workflow executes the definition stored at the tagged ref, while the release
authority has to come from the reviewed workflow on trusted `main`.

The run then proceeds in four stages, each gating the next:

1. **authorize** — a standards-owned reusable workflow, pinned to a full
   40-character commit SHA, checks out this repository's reviewed `main`,
   rejects a lightweight or non-stable tag, verifies the SSH signature against
   the committed `.github/allowed_signers`, proves the tagged commit is
   reachable from current `origin/main`, and returns the commit and the
   immutable tag-object identifier.
2. **build** — checks out that exact commit under `contents: read`, requires the
   tag and `pyproject.toml` versions to agree and a CHANGELOG section to exist,
   re-runs `make verify`, `make demo` and `make package-check`, generates an
   SBOM, records checksums, issues a GitHub build-provenance attestation, and
   signs `dist/SHA256SUMS` with keyless cosign.
3. **github-release** — creates or updates the GitHub release and uploads the
   candidate. It never checks out or executes repository code, and it
   re-compares the live tag object against the authorizer's identifier
   immediately before publishing, so a tag moved after authorization fails here.
4. **pypi-publish**, then **verify-published** — uploads the two distributions
   the build attested, after re-checking their digests against the manifest it
   was handed, and then installs the published version from PyPI and invokes it.

Publication authority is confined to stages 3 and 4. The job that executes
repository code cannot publish what it built, every other workflow in this
repository is forbidden to publish anything at all, and
`tests/test_supply_chain.py` asserts that confinement as a merge-blocking
boundary — including that the PyPI upload uses Trusted Publishing and that no
long-lived registry credential is referenced anywhere.

Until 2026-09-06 there was no stage 3 or 4 at all. The gap was recorded as a
decision rather than an omission, waived as WVR-009 against the portfolio's
`release_workflow` control. That waiver named its own retirement trigger — "the
control becomes implementable in the same change that adds it" — and was retired
on it.

## What is in place

- initialized version control and a hosted public repository (`gh repo view
  --json isPrivate` returns false);
- protected main and tag rulesets with required checks (`protect-tags`
  additionally requires signed, immutable tags — deletion and rewrite of a
  matching ref are rejected by GitHub, not just by CI);
- SBOM and a distributable artifact signature (build provenance attestation
  and a keyless cosign signature over `dist/SHA256SUMS` are both issued per
  candidate);
- incident labels (`security`, `incident`);
- a security contact route: private vulnerability reporting is enabled, so the
  repository Security tab accepts a private advisory. It is confirmable rather
  than asserted — `GET /repos/ChelseaKR/obligation-receipts/private-vulnerability-reporting`
  returns `{"enabled": true}`. See `SECURITY.md`; and
- signed tags and verified maintainer identity. `v0.1.0` is an annotated
  SSH-signed tag; it verifies locally against `.github/allowed_signers`, and
  GitHub's own verification reports `"verified": true`, so the release-signing
  key is registered under the maintainer's account as a signing key. This
  document previously said no tag had been cut and that the key still needed
  registering; both halves have since happened.

## What is still required before anything is published

Each of these needs a person, not a commit.

- **A PyPI Trusted Publisher for this project.** The upload job authenticates
  with the OIDC claim GitHub mints for it; PyPI has to be told once, through its
  web interface, to trust that claim. Until then `pypi-publish` fails with a
  trust error, which is the correct outcome — the alternative is a stored API
  token, and this repository refuses one. The pending-publisher settings are:
  owner `ChelseaKR`, repository `obligation-receipts`, workflow `release.yml`,
  environment `pypi`. The name to reserve is `obligation-receipts`, which is
  unregistered on PyPI as of 2026-09-06.
- **An independently reviewed release decision** — a second maintainer or
  outside reviewer signing off on cutting a specific version, distinct from the
  automated `verify`/`authorize` gates. The `pypi` environment is where a
  required reviewer would be attached, if that is how the review is enforced.
- **A decision about which tag to publish.** `v0.1.0`'s own annotation says
  "Build-and-attest candidate only: no publication authority, no package index."
  Publishing that tag would contradict the message signed into it. A new tag
  whose annotation says what it is avoids the contradiction.
- **Discovery evidence supporting continued product development** — the sample
  pack is unrated candidate selection only (see
  `docs/discovery/public-sample-candidates.md`); it needs a selection owner and
  two independent raters to actually complete it. `docs/ROADMAP.md` lists a
  signed release pipeline under M1, which is gated on discovery's proceed
  thresholds; the pipeline existing is not the same as those thresholds passing.
- **Exact package URLs** — these resolve once a package is actually published to
  a registry; `SECURITY.md` commits in advance to the README and release notes
  as the only canonical source.
