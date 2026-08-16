#!/usr/bin/env bash
#
# Deploy Campaign Factory to Cloud Run from Google Cloud Shell.
#
#   ./deploy/deploy.sh              # show the plan, then ask before deploying
#   ./deploy/deploy.sh --yes        # skip the confirmation
#
# Everything is overridable by environment variable; see CONFIG below.
#
set -euo pipefail

# ── CONFIG ─────────────────────────────────────────────────────────────────
SERVICE="${SERVICE:-campaign-factory}"
REGION="${REGION:-asia-east1}"
# Resolved after the gcloud check below — a bare $(gcloud ...) here would abort
# the script under `set -e` if gcloud is missing, before any useful message.
PROJECT_ID="${PROJECT_ID:-}"

# Campaign data is written to the container's own filesystem, and the write
# lock (app/utils/file_handler.py) is a threading.Lock, which only serialises
# writers inside ONE process. Two instances therefore means:
#   - each serves a different, diverging copy of every campaign, and
#   - concurrent writes silently overwrite each other.
# Until storage moves off the container disk, this MUST stay at 1.
MAX_INSTANCES="${MAX_INSTANCES:-1}"

# Keeping one instance warm stops Cloud Run from reclaiming the container
# between requests, which is what destroys the data directory. It reduces the
# window; it does NOT make storage durable. A deploy, a crash, or a platform-
# initiated restart still wipes everything. Export campaigns you care about.
MIN_INSTANCES="${MIN_INSTANCES:-1}"

MEMORY="${MEMORY:-1Gi}"
CPU="${CPU:-1}"
# Plan generation chains two LLM calls and can run for minutes; the Cloud Run
# default of 300s cuts it off mid-request.
TIMEOUT="${TIMEOUT:-900}"

# Non-secret runtime config.
ENV_VARS="${ENV_VARS:-APP_ENV=production,DEFAULT_LANGUAGE=zh,DATA_DIR=/app/data}"

# Secret Manager secrets, mapped to the env vars the app reads. Leave empty to
# skip. Format: ENV_NAME=secret-name:version,...
SECRETS="${SECRETS:-}"

# ── PRE-FLIGHT ─────────────────────────────────────────────────────────────
if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud not found. Run this from Google Cloud Shell, or install" >&2
  echo "       the Google Cloud SDK: https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
# Older gcloud prints the literal string "(unset)" instead of nothing.
[[ "$PROJECT_ID" == "(unset)" ]] && PROJECT_ID=""

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: no project set. Run:  gcloud config set project YOUR_PROJECT_ID" >&2
  echo "       ...or pass one:      PROJECT_ID=my-project ./deploy/deploy.sh" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f Dockerfile ]]; then
  echo "ERROR: run this from the repository (no Dockerfile found in $REPO_ROOT)." >&2
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
DIRTY=""
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
  DIRTY="  (uncommitted changes present — they WILL be deployed)"
fi

cat <<PLAN

  Deploying Campaign Factory
  ──────────────────────────────────────────────
  project        $PROJECT_ID
  service        $SERVICE
  region         $REGION
  source         $BRANCH @ $COMMIT$DIRTY
  instances      min=$MIN_INSTANCES  max=$MAX_INSTANCES
  resources      cpu=$CPU  memory=$MEMORY  timeout=${TIMEOUT}s
  env            $ENV_VARS
  secrets        ${SECRETS:-<none>}

PLAN

if [[ "$MAX_INSTANCES" != "1" ]]; then
  cat <<'WARN'
  ⚠  MAX_INSTANCES is not 1.

     Campaign data lives on the container filesystem and the write lock is
     per-process. With more than one instance, users will see different data
     depending on which instance they hit, and concurrent edits will be lost.

     Only proceed if storage has been moved off the container disk.

WARN
fi

if [[ "${1:-}" != "--yes" ]]; then
  read -r -p "  Proceed? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || { echo "  Aborted."; exit 0; }
fi

# ── DEPLOY ─────────────────────────────────────────────────────────────────
DEPLOY_ARGS=(
  run deploy "$SERVICE"
  --source .
  --project "$PROJECT_ID"
  --region "$REGION"
  --platform managed
  --max-instances "$MAX_INSTANCES"
  --min-instances "$MIN_INSTANCES"
  --memory "$MEMORY"
  --cpu "$CPU"
  --timeout "$TIMEOUT"
  --set-env-vars "$ENV_VARS"
)
[[ -n "$SECRETS" ]] && DEPLOY_ARGS+=(--set-secrets "$SECRETS")

# Note: no --allow-unauthenticated / --no-allow-unauthenticated here. Passing
# either would silently change who can reach the service; the existing IAM
# policy is preserved and reported below instead.
gcloud "${DEPLOY_ARGS[@]}"

# ── POST-DEPLOY REPORT ─────────────────────────────────────────────────────
URL="$(gcloud run services describe "$SERVICE" \
        --project "$PROJECT_ID" --region "$REGION" \
        --format='value(status.url)' 2>/dev/null || true)"

echo
if [[ -z "$URL" ]]; then
  echo "  Deployed, but could not read the service URL. Check:"
  echo "    gcloud run services describe $SERVICE --region $REGION"
  exit 1
fi
echo "  Deployed: $URL"

if gcloud run services get-iam-policy "$SERVICE" \
     --project "$PROJECT_ID" --region "$REGION" --format=json 2>/dev/null \
   | grep -q 'allUsers'; then
  cat <<'PUBLIC'

  ⚠  This service is reachable by anyone on the internet.

     There is no authentication in the application itself, so that means any
     caller can list every campaign, read competitor analysis, and spend your
     LLM quota via /api/parse-brief.

     To require a Google identity:
       gcloud run services remove-iam-policy-binding SERVICE \
         --region REGION --member=allUsers --role=roles/run.invoker

PUBLIC
fi

echo "  Health check:"
if curl -fsS --max-time 30 "$URL/" -o /dev/null; then
  echo "    OK — serving"
else
  echo "    FAILED — check logs:"
  echo "    gcloud run services logs read $SERVICE --region $REGION --limit 50"
  exit 1
fi

cat <<ROLLBACK

  Rollback (previous revision):
    gcloud run revisions list --service $SERVICE --region $REGION --limit 5
    gcloud run services update-traffic $SERVICE --region $REGION --to-revisions REVISION=100

ROLLBACK
