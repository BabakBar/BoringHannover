#!/usr/bin/env bash
# Routing contract for the production nginx config.
#
# Guards the regression that caused the Search Console "Alternate page with
# proper canonical tag" report: an SPA-style fallback served the homepage with
# HTTP 200 for every unknown URL, so expired /special/ pages looked to Google
# like duplicates of "/".
#
# Usage: scripts/smoke-routing.sh          (builds web/dist if missing)
#        scripts/smoke-routing.sh --no-build
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Derive the nginx image from the production Dockerfile so the smoke test can
# never drift from what actually serves the site.
IMAGE="$(grep -oE '^FROM nginx:[^ ]+' "$REPO_ROOT/Dockerfile.web" | head -1 | cut -d' ' -f2)"
CONTAINER="boringhannover-smoke-$$"
PORT="${SMOKE_PORT:-18099}"
FAILED=0

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [[ "${1:-}" != "--no-build" && ! -f "$REPO_ROOT/web/dist/index.html" ]]; then
  echo "==> Building web/dist"
  (cd "$REPO_ROOT/web" && bun run build)
fi

if [[ ! -f "$REPO_ROOT/web/dist/index.html" ]]; then
  echo "ERROR: web/dist/index.html missing; build the site first" >&2
  exit 1
fi

echo "==> Starting $IMAGE on :$PORT"
docker run -d --name "$CONTAINER" -p "$PORT:8080" \
  -v "$REPO_ROOT/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$REPO_ROOT/web/dist:/usr/share/nginx/html:ro" \
  "$IMAGE" >/dev/null

ready=0
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/health" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: nginx did not become ready on :$PORT" >&2
  docker logs "$CONTAINER" 2>&1 | tail -20 >&2
  exit 1
fi

# Pinned to 127.0.0.1 (not "localhost", which also resolves to ::1) and
# tolerant of transport blips: a failed curl must be reported as a failed
# assertion, never abort the run under `set -e`.
BASE="http://127.0.0.1:$PORT"
CURL=(curl -s --retry 2 --retry-connrefused --max-time 10)

# expect <path> <status> [description]
expect() {
  local path="$1" want="$2" desc="${3:-}"
  local got
  got="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE$path" || echo 000)"
  if [[ "$got" == "$want" ]]; then
    printf '  ok    %-34s %s\n' "$path" "$got"
  else
    printf '  FAIL  %-34s got %s, want %s %s\n' "$path" "$got" "$want" "$desc"
    FAILED=1
  fi
}

# expect_redirect <path> <expected Location>
expect_redirect() {
  local path="$1" want="$2"
  local got
  got="$("${CURL[@]}" -o /dev/null -D - "$BASE$path" 2>/dev/null \
    | awk 'tolower($1)=="location:"{print $2}' | tr -d '\r' || true)"
  if [[ "$got" == "$want" ]]; then
    printf '  ok    %-34s -> %s\n' "$path" "$got"
  else
    printf '  FAIL  %-34s Location %s, want %s\n' "$path" "${got:-<none>}" "$want"
    FAILED=1
  fi
}

echo "==> Unknown routes must 404, never fall back to the homepage"
expect /does-not-exist/ 404
expect /special/expired-occasion/ 404 "expired occasion must not 200"
expect /404.html 404 "the 404 page itself must not be indexable as 200"

echo "==> Real pages still resolve"
expect / 200
expect /impressum/ 200
expect /special/ 200
expect /sitemap.xml 200
expect /robots.txt 200
expect /health 200

echo "==> One URL per page: redirect to the canonical trailing-slash form"
expect /impressum 301
expect_redirect /impressum /impressum/
expect_redirect '/impressum?a=1&b=2' '/impressum/?a=1&b=2'

echo "==> Redirects stay relative so the internal :8080 never leaks"
if "${CURL[@]}" -o /dev/null -D - "$BASE/impressum" 2>/dev/null \
  | grep -qi '^location:.*8080'; then
  echo "  FAIL  Location header leaked the container port"
  FAILED=1
else
  echo "  ok    no port leak in Location"
fi

echo "==> Dead config files are not served"
expect /_headers 403

echo "==> Assets are untouched by the redirect rule"
css="$(grep -o '/assets/[A-Za-z0-9._-]*\.css' "$REPO_ROOT/web/dist/index.html" | head -1)"
[[ -n "$css" ]] && expect "$css" 200 "hashed asset"

# The about dialog is a native <dialog>, centred by the UA stylesheet's
# `margin: auto`. Tailwind v4's Preflight resets `margin: 0` on every element,
# which pinned it to the top-left corner until Header.astro put the centring
# back. Assert on what nginx actually serves, so the rule cannot be lost in a
# refactor or dropped somewhere between the source and the bundle.
echo "==> The about dialog keeps the margin that centres it"
if "${CURL[@]}" "$BASE/" | grep -qE 'about-dialog\[data-astro-cid-[a-z0-9]+\]\{[^}]*margin: ?auto'; then
  echo "  ok    about dialog centred"
else
  echo "  FAIL  about dialog lost margin:auto; it will render in the top-left corner"
  FAILED=1
fi

if [[ "$FAILED" -ne 0 ]]; then
  echo "SMOKE FAILED" >&2
  exit 1
fi
echo "All routing checks passed."
