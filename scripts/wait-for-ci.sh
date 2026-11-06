#!/usr/bin/env bash
# Never publish an outdated revision or one whose required CI jobs did not pass.
set -euo pipefail

: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
: "${GH_TOKEN:?GH_TOKEN must be set}"
sha="${1:?Usage: wait-for-ci.sh <commit-sha> [timeout-seconds]}"
timeout="${2:-900}"
[[ "${sha}" =~ ^[a-f0-9]{40}$ && "${timeout}" =~ ^[0-9]+$ ]] || exit 1
api="${GITHUB_API_URL:-https://api.github.com}"
deadline=$((SECONDS + timeout))
expected='["Version pins in sync","Backend (Python 3.14)","Backend (Python 3.15)","Frontend (Bun)","Workflow audit (zizmor)","Docker Build"]'

fail() { echo "::error::$1" >&2; exit 1; }
get() {
  curl --fail --silent --show-error --max-time 30 \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "${api}/repos/${GITHUB_REPOSITORY}/$1"
}

printf 'Waiting for same-revision CI for %s (timeout %ss)\n' "${sha}" "${timeout}"
while true; do
  current="$(get git/ref/heads/master | jq -er '.object.sha')"
  [ "${current}" = "${sha}" ] || fail "Selected revision is no longer master; refusing deployment."
  runs="$(get "actions/workflows/ci.yml/runs?head_sha=${sha}&branch=master&per_page=100")"
  # A PR run can have the same SHA; it must never authorize a privileged release.
  # Select the newest run rather than finding any older successful attempt.
  run="$(jq -c --arg sha "${sha}" --arg repo "${GITHUB_REPOSITORY}" '
    [.workflow_runs[] | select(
      .head_sha == $sha and .head_branch == "master" and
      .head_repository.full_name == $repo and .path == ".github/workflows/ci.yml" and
      (.event == "push" or .event == "workflow_dispatch")
    )] | max_by(.id) // empty' <<< "${runs}")"
  if [ -n "${run}" ] && [ "$(jq -r '.status' <<< "${run}")" = "completed" ]; then
    [ "$(jq -r '.conclusion' <<< "${run}")" = "success" ] || fail "Latest same-revision CI did not succeed."
    id="$(jq -er '.id | numbers' <<< "${run}")"
    attempt="$(jq -er '.run_attempt | numbers' <<< "${run}")"
    jobs="$(get "actions/runs/${id}/attempts/${attempt}/jobs?per_page=100")"
    # A green workflow can contain skipped jobs. Check every required job in the
    # selected attempt, and fail closed if the response is incomplete.
    jq -e --argjson expected "${expected}" --arg sha "${sha}" '
      .jobs as $jobs | .total_count == ($jobs | length) and
      all($expected[]; . as $name |
        [$jobs[] | select(.name == $name)] |
        length == 1 and .[0].status == "completed" and
        .[0].conclusion == "success" and .[0].head_sha == $sha
      )' <<< "${jobs}" >/dev/null || fail "Required same-revision CI jobs are missing or unsuccessful."
    printf 'CI validated %s (run %s, attempt %s)\n' "${sha}" "${id}" "${attempt}"
    exit 0
  fi
  [ "${SECONDS}" -lt "${deadline}" ] || fail "Timed out waiting for same-revision CI."
  sleep 10
done
