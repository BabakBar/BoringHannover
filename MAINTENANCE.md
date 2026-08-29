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
- `bun install --frozen-lockfile` — the lockfile is complete and installs deterministically
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

### Base images

Both images apply the distribution's outstanding security updates at build time
(`apt-get upgrade` for Debian, `apk upgrade` for Alpine). Without that, an image
ships whatever packages were current when the upstream base was last published,
which is typically weeks behind — the OpenSSL advisory that first tripped this
gate was exactly that case.

The trade is explicit: **container images are patched at build time and are
therefore not bit-reproducible.** The same commit built tomorrow can contain
different distribution packages. What *is* reproducible is the application
layer — `uv.lock` and `bun.lock` pin every dependency, and CI proves a clean
install matches them. What identifies a given build is its digest, recorded in
the deploy summary. Do not describe these image builds as reproducible; the
guarantee they offer is "patched whenever rebuilt, and identifiable afterwards".

The alternative — pinning both base images by digest and letting Dependabot
update those digests — buys reproducibility at the cost of leaving a fresh CVE
unpatched until the next digest bump. That trade is worth revisiting if release
provenance ever needs to be byte-exact.

The backend runtime image also removes `pip`. The application runs from
`/app/.venv` and never installs anything at runtime, while pip's *vendored*
copies of `msgpack` and `setuptools` were the only vulnerable Python packages a
scan of the image could find. Removing pip is both the fix and a smaller
attack surface; nothing in the image needs it.

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

## Repository settings auto-merge depends on

Two settings must be enabled before any dependency update merges itself
(Settings → General, and Settings → Branches):

1. **Allow auto-merge.**
2. **Branch protection on `master` requiring the CI checks** — `Version pins in
   sync`, `Backend (Python 3.13)`, `Backend (Python 3.14)`, `Frontend (Bun)`,
   `Workflow audit (zizmor)`, `Docker Build`.

`gh pr merge --auto` only waits for checks a branch actually *requires*. On an
unprotected branch there is nothing to wait for, so the merge happens
immediately — before CI has run. Setting (2) is what makes "green CI" the real
gate; setting (1) is what makes `--auto` queue rather than merge on the spot.

**Until both are set, nothing auto-merges.** Before queueing a merge the
workflow asks GitHub which checks are *required* on the base branch and stands
down — labelling `needs-review` and commenting which checks are missing —
unless all six are there. It reads both the rules API (rulesets) and the pull
request's own required checks (classic branch protection), so it is correct
under either mechanism. Note that a branch protected by a ruleset returns
`404 Branch not protected` from the *classic* protection endpoints — that is
the expected answer, not an absence of protection; inspect rulesets with
`gh api repos/BabakBar/BoringHannover/rules/branches/master` instead. Partial protection is the case worth guarding
against: a branch that requires only a review, or only one check, still reports
the pull request as "blocked" while leaving CI free to be red at merge time.

Because the workflow matches those checks **by name**, renaming a CI job means
updating the required checks in branch protection *and* the expected list in
`.github/workflows/dependabot-auto-merge.yml`. Until both agree, updates wait
for a human rather than merging — the failure is loud and safe, not silent.

### Making an auto-merged update deploy itself

A merge performed with `GITHUB_TOKEN` does not raise a `push` event —
[GitHub suppresses workflow runs triggered by its own token](https://docs.github.com/en/actions/concepts/security/github_token)
to prevent recursion. Left alone, an auto-merged dependency update would land on
`master` without CI or Deploy running, and production would quietly sit behind.

The workflow therefore merges with a **GitHub App installation token** when one
is configured, which does raise `push`. Without the secrets it falls back to
`GITHUB_TOKEN` and logs which token it used; in that case refresh production by
dispatching Deploy manually.

**Setting up the App (once):**

1. **Create it** — Settings → Developer settings → GitHub Apps → *New GitHub App*
   (a personal App is fine). Name it something like `boringhannover-automerge`,
   set any homepage URL, and **uncheck Webhook → Active** (it receives nothing).
2. **Permissions** — Repository permissions only:
   - *Contents*: **Read and write** (performing the merge)
   - *Pull requests*: **Read and write** (enabling auto-merge)
   Nothing else. Leave every organisation and account permission at *No access*.
3. **Install it** on `BabakBar/BoringHannover` only — *Install App* → **Only
   select repositories**.
4. **Credentials** — on the App's page note the **App ID**, then *Generate a
   private key* and keep the downloaded `.pem`.
5. **Repository secrets** (Settings → Secrets and variables → Actions):
   - `AUTOMERGE_APP_ID` — the App ID
   - `AUTOMERGE_APP_PRIVATE_KEY` — the entire `.pem` contents, including the
     `-----BEGIN...` and `-----END...` lines
6. **Let it through the ruleset** — if the branch ruleset requires approving
   reviews, add the App to that rule's **bypass list**; a Dependabot PR will
   never collect a human approval, so without this nothing merges. Required
   *status checks* need no bypass: waiting for them is the point.
7. **Verify** on the next Dependabot PR: the merge step logs `Merging with a
   GitHub App token`, and after the merge a CI **and** a Deploy run appear on
   `master`.

Rotate the private key like any other credential; revoking it makes the
workflow fall back to `GITHUB_TOKEN` rather than fail.

## Ownership

The repository owner reviews major updates, triages scanner findings and owns
suppressions. Automation handles everything else. If the weekly Security Audit
issue stays open for more than a cycle, that is the signal that this policy is
being ignored — a permanently red dashboard is not a control.
