# Maintenance

How dependencies, images and the pipeline stay current without babysitting, and
what still needs a human.

## Runtimes

| Component | Pinned in |
|---|---|
| Python 3.14 (production), 3.13 (minimum, also tested) | `Dockerfile`, `.python-version`, `pyproject.toml` |
| uv | `Dockerfile`, workflow `UV_VERSION` |
| Bun | `web/.bun-version`, `Dockerfile.web`, `docker-compose.yml` |
| Trivy | `scripts/trivy-scan.sh` (by digest) |
| nginx | `Dockerfile.web` |

The CI `pins` job fails when these disagree across files.

## How updates arrive

| Update | Owner | Merge |
|---|---|---|
| Python and frontend packages within their ranges, incl. transitive | `dependency-refresh.yml`, Fridays 12:00 Berlin, one PR | Auto, once required checks pass |
| Bun, uv, zizmor, Trivy patch releases | same PR | Auto |
| Python majors, prereleases, downgrades, pre-1.0 minors | same PR, auto-merge off | **You** |
| Bun, uv, zizmor, Trivy minor/major releases | same PR, auto-merge off | **You** |
| Frontend package majors | Dependabot, one PR each | **You** |
| Python and nginx base images | Dependabot (patch/minor grouped) | Auto; majors **you** |
| GitHub Action SHAs | Dependabot (patch/minor grouped) | Auto; majors **you** |
| Security advisories | Dependabot security PRs, immediately | **You** |

New releases wait 7 days (14 for majors) before Dependabot proposes them.
Framework migrations (Astro, Tailwind, Python) are hand-written PRs: follow the
upstream guide, run the full build and tests, and compare rendered text on real
pages (Astro 7's `compressHTML: 'jsx'` once turned "25 Aug" into "25Aug"; this
repo keeps `compressHTML: true`).

## Gates

Every PR, including automated ones, passes: lockfiles current (`uv lock --check`,
`bun install --frozen-lockfile`), ruff, ty, pytest on 3.13 and 3.14, frontend
tests and build, the nginx routing smoke test, the end-to-end pipeline test,
`uv audit` and `bun audit`, zizmor, and a Trivy scan of both images (no fixable
HIGH/CRITICAL). Deploy scans the published images again and will not ship a
failing one. `security.yml` re-audits master weekly and keeps one tracking issue
open while it finds something.

## Vulnerabilities

| Severity | Response |
|---|---|
| CRITICAL | Fix or mitigate within 24 hours |
| HIGH | Fix within 7 days |
| MEDIUM / LOW | Next refresh, or an expiring suppression |

Scans use `--ignore-unfixed`. A suppression goes in `.trivyignore` with an owner,
a reason and a review date:

```
# CVE-2026-12345 — <package>
# Owner: <github handle>
# Reason: not reachable; requires the <x> feature, unused here.
# Review by: 2026-12-01
CVE-2026-12345
```

Images apply OS security updates at build time, so a rebuild of the same commit
can differ; the digest identifies a build. The backend image has no `pip`.

## Rollback

Image tags (`latest`, commit SHA) float; the digest in each deploy run's summary
does not. Roll back by pinning the Coolify service to the last good digest. Keep
at least 10 image versions in GHCR. Provenance:
`gh attestation verify oci://ghcr.io/babakbar/boringhannover/backend@<digest> --repo BabakBar/BoringHannover`

## Settings auto-merge depends on

1. **Allow auto-merge** (Settings → General).
2. **Required checks on `master`**: `Version pins in sync`, `Backend (Python 3.13)`,
   `Backend (Python 3.14)`, `Frontend (Bun)`, `Workflow audit (zizmor)`, `Docker Build`.
   Both auto-merge workflows check this list and stand down if any is missing.
   Renaming a CI job means updating branch protection and both lists.
3. **GitHub App** (`AUTOMERGE_APP_ID`, `AUTOMERGE_APP_PRIVATE_KEY` secrets), so merges
   raise `push` and CI + Deploy run. Repository permissions: Contents, Pull requests
   and Workflows read/write; installed on this repository only; on the ruleset's
   bypass list if reviews are required. Without it Dependabot merges fall back to
   `GITHUB_TOKEN` and Deploy must be dispatched by hand; the refresh fails visibly.

Actions are pinned to commit SHAs; zizmor fails CI on an unpinned one.

## Repository traffic archive

GitHub keeps traffic for 14 days. `traffic-analytics.yml` (03:00 and 15:00 UTC)
merges it losslessly into the `traffic-data` branch, served at
<https://babakbar.github.io/BoringHannover/>. It needs a `TRAFFIC_TOKEN` secret
(classic PAT with `repo`, or fine-grained with Administration: read and
Contents: write). A failed fetch, missing token or unreadable archive fails the
run without writing, so the archive is never overwritten by a partial snapshot.

Known gaps: views and clones start 2026-08-21 (a partial day); stars and forks
are complete from 2025-12-16; unique visitors and cloners are summed per day.
