# Dependency, runtime and supply-chain maintenance

This is the policy the automation implements. It answers issue #35: what we run,
how updates arrive, who reviews them, what gates they pass, and how a bad
deployment is rolled back.

The rule behind all of it: **drift is paid for either continuously or all at
once.** The all-at-once bill for this repository was Astro 4 → 7 and Tailwind
3 → 4 in a single PR. The point of everything below is to never send that
invoice again.

## Supported runtimes and toolchain

| Component | Version | Pinned in | Notes |
|---|---|---|---|
| Python (production) | 3.14 | `Dockerfile`, `.python-version` | Runtime for the scraper image |
| Python (minimum supported) | 3.13 | `pyproject.toml` (`requires-python`) | Also tested in CI |
| uv | 0.12.6 | `Dockerfile`, `ci.yml` (`UV_VERSION`) | Resolver + lockfile owner |
| Bun | 1.4.0 | `web/.bun-version`, `Dockerfile.web`, `docker-compose.yml` | Frontend build + test runner |
| Astro | 7.x | `web/package.json` | Static output, no adapter |
| Tailwind CSS | 4.x | `web/package.json` | Via `@tailwindcss/vite`, CSS-first config |
| nginx | 1.30-alpine (stable) | `Dockerfile.web` | Serves the built site |
| Browser baseline | Safari 16.4+, Chrome 111+, Firefox 128+ | — | Set by Tailwind 4; do not regress without a decision |

CI runs the backend on **both** 3.13 and 3.14. Raising the floor is then a
one-line change to `requires-python`, not an investigation.

The `pins` job in CI fails the build if these versions disagree across
`Dockerfile`, `Dockerfile.web`, `docker-compose.yml`, `.python-version` and the
workflow env. A pin that lives in four files is a pin that silently rots in
three of them.

## Update cadence

| Change | How it arrives | Who reviews | Merge |
|---|---|---|---|
| Patch / minor (all ecosystems) | One grouped Dependabot PR per ecosystem, Mondays 05:00 Europe/Berlin | Nobody, if CI is green | Auto-merged (squash) |
| Major | Its own Dependabot PR, labelled `major-update` / `needs-review` | Repository owner | Manual, never auto |
| Security advisory | Dependabot security PR, immediately — ignores schedule, groups and PR limits | Repository owner | Manual, prioritised per SLA below |
| Framework migration (Astro, Tailwind, Python major) | Hand-written PR from its own issue | Repository owner | Manual, with the evidence listed under *Major migrations* |

A **7-day cooldown** (14 for majors) keeps a release out of this repository
until upstream has had a chance to yank it. Security updates bypass it.

Automation opens PRs. Automation does not decide that a framework should be
replaced.

## Required gates

Every PR, including every Dependabot PR, must pass:

- `uv lock --check` — the lockfile matches `pyproject.toml`
- `bun install --frozen-lockfile` — the lockfile is complete and reproducible
- ruff lint + format, `ty` type check, pytest (Python 3.13 **and** 3.14)
- `bun run test`, `bun run build`, nginx routing smoke test
- `uv audit` and `bun audit` — no known-vulnerable dependency
- `zizmor` — workflow hardening (unpinned actions, over-broad permissions,
  injection sinks)
- Both container images build, and Trivy finds no fixable HIGH/CRITICAL

Nothing deploys that has not passed all of it.

## Vulnerability severity and response

| Severity | Response |
|---|---|
| CRITICAL | Fix or mitigate within 24 hours; if no fix exists upstream, mitigate at the edge (nginx, network) and record the exception |
| HIGH | Fix within 7 days |
| MEDIUM | Next weekly grouped update |
| LOW | Next weekly grouped update, or accept with an expiring suppression |

Scanners run with `--ignore-unfixed`: a finding with no upstream fix is not a
merge blocker, because blocking on it only teaches everyone to ignore red.
Those findings still surface in the weekly Security Audit run.

### Suppressions

A suppression is a dated decision, not a mute button. Record it in
`.trivyignore` (or the relevant scanner's ignore file) in this format:

```
# CVE-2026-12345 — <package>
# Owner: <github handle>
# Reason: not reachable; the vulnerable code path requires the <x> feature, unused here.
# Review by: 2026-12-01
CVE-2026-12345
```

Every entry needs an owner, a reason and a review date. An entry past its review
date is a bug and should fail review.

## Major migrations

Astro, Tailwind, Python and Bun majors are **separate, reversible PRs**, never
combined with each other or with product work. Each one needs:

1. the upstream migration guide followed explicitly, with deviations noted;
2. a full build plus the test suite on the target version;
3. before/after evidence on the real pages — rendered text compared for
   equality, and rendered screenshots compared for unintended layout change;
4. an explicit list of the visual or behavioural changes that are intentional.

Rendered-text equality is the cheap check that catches the expensive class of
bug: Astro 7's `compressHTML: 'jsx'` default silently deletes the space between
adjacent inline elements ("25 Aug" → "25Aug"). This repository keeps
`compressHTML: true` for that reason.

## Deployment, traceability and rollback

- Images publish a commit-SHA tag and `latest`. Both float. **The digest is the
  rollback reference** — it is recorded in every deploy run's summary alongside
  the commit.
- Every published image carries an SBOM and signed SLSA build provenance
  (`actions/attest-build-provenance`, pushed to the registry). Verify with:
  `gh attestation verify oci://ghcr.io/babakbar/boringhannover/backend@<digest> --repo BabakBar/BoringHannover`
- To roll back: pin the Coolify service to the previous digest from the last
  known-good deploy summary. Do not rely on `latest`.
- Keep at least the last 10 image versions in GHCR so a rollback has somewhere
  to go.

## GitHub Actions

Actions are pinned to **full commit SHAs** with the version in a trailing
comment. Tags are mutable — in March 2026, 75 of 76 `trivy-action` version tags
were force-pushed in a supply-chain attack, and pipelines that trusted tags
leaked their secrets. Trivy therefore runs here from its official image pinned
by digest, not via the action.

Dependabot's `github-actions` ecosystem updates both the SHA and the comment, so
pinning stays maintainable. `zizmor` fails CI if an unpinned action appears.

## Repository settings this depends on

Two settings must be enabled for auto-merge to behave as described (Settings →
General, and Settings → Branches):

1. **Allow auto-merge.**
2. **Branch protection on `master` requiring the CI checks** — `Backend
   (Python 3.13)`, `Backend (Python 3.14)`, `Frontend (Bun)`, `Docker Build`,
   `Workflow audit (zizmor)`, `Version pins in sync`.

Without (2), `gh pr merge --auto` has no checks to wait for and would merge
immediately. Setting (2) is what makes "green CI" the actual gate.

## Ownership

The repository owner reviews major updates, triages scanner findings and owns
suppressions. Automation handles everything else. If the weekly Security Audit
issue stays open for more than a cycle, that is the signal that this policy is
being ignored — a permanently red dashboard is not a control.
