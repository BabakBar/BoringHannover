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

TRIVY_IMAGE="aquasec/trivy:0.76.2@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"

vulnerable=""
errored=""
for arg in "$@"; do
  name="${arg%%=*}"
  ref="${arg#*=}"
  rc=0
  # The default Google mirror can return blob 404s that prevent fallback.
  # Use the official registries directly, with ECR for transient GHCR failures.
  docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${HOME}/.cache/trivy:/root/.cache/trivy" \
    -e TRIVY_USERNAME -e TRIVY_PASSWORD \
    "${TRIVY_IMAGE}" \
    image --scanners vuln --severity HIGH,CRITICAL \
    --db-repository ghcr.io/aquasecurity/trivy-db:2 \
    --db-repository public.ecr.aws/aquasecurity/trivy-db:2 \
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
