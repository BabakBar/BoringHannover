#!/usr/bin/env bash
# Fail on fixable HIGH/CRITICAL vulnerabilities in container images.
#
# Usage: scripts/trivy-scan.sh <name>=<image-ref> [...]
#
# Every image is scanned before failing, so one run reports all findings.
# Trivy exits 2 on a finding and 1 when it could not scan at all (bad
# reference, registry auth, network): both fail, but they need different
# fixes, so they are reported separately. TRIVY_USERNAME/TRIVY_PASSWORD are
# passed through for private registry pulls.
#
# Trivy runs from its image pinned by digest: the trivy-action tags were
# force-pushed in a March 2026 supply-chain attack.
set -uo pipefail

TRIVY_IMAGE="aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa"

vulnerable=""
errored=""
for arg in "$@"; do
  name="${arg%%=*}"
  ref="${arg#*=}"
  rc=0
  docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${HOME}/.cache/trivy:/root/.cache/trivy" \
    -e TRIVY_USERNAME -e TRIVY_PASSWORD \
    "${TRIVY_IMAGE}" \
    image --scanners vuln --severity HIGH,CRITICAL \
    --ignore-unfixed --exit-code 2 --no-progress "${ref}" || rc=$?
  case "${rc}" in
    0) echo "${name}: clean (${ref})" ;;
    2) vulnerable="${vulnerable} ${name}" ;;
    *) errored="${errored} ${name}" ;;
  esac
done

if [ -n "${errored}" ]; then
  echo "::error::Trivy could not scan (scanner error, not a finding):${errored}"
fi
if [ -n "${vulnerable}" ]; then
  echo "::error::HIGH/CRITICAL vulnerabilities found:${vulnerable}"
fi
[ -z "${errored}${vulnerable}" ]
