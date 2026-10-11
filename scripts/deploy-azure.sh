#!/usr/bin/env bash
# Deploy the Ingredion agentic-AI demo service to Azure Container Apps.
#
# This is the simplest reliable portfolio target: serverless containers with
# scale-to-zero. The repo also ships an enterprise AKS + Terraform path
# (infra/terraform/); see DEPLOYMENT.md for how to switch.
#
# Prerequisites (do these yourself first — the script never logs in for you):
#   1. Install the Azure CLI: https://learn.microsoft.com/cli/azure/install-azure-cli
#   2. az login
#   3. An Azure subscription where you can create resource groups.
#
# Usage:
#   ./scripts/deploy-azure.sh            # offline demo mode (no LLM keys needed)
#   ./scripts/deploy-azure.sh --live     # live Azure OpenAI mode; requires
#                                        # AZURE_OPENAI_ENDPOINT and
#                                        # AZURE_OPENAI_CHAT_DEPLOYMENT env vars
#
# Optional env overrides: RESOURCE_GROUP, LOCATION, APP_NAME, ACR_NAME, IMAGE_TAG.
#
# Idempotent: safe to re-run. Existing resources are reused; the container app
# is updated in place when it already exists.
set -euo pipefail

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-ingredion-agents-rg}"
LOCATION="${LOCATION:-eastus}"
APP_NAME="${APP_NAME:-ingredion-agentic-ai}"
ENV_NAME="${APP_NAME}-env"
IMAGE_TAG="${IMAGE_TAG:-latest}"
LIVE_MODE=false
if [[ "${1:-}" == "--live" ]]; then
  LIVE_MODE=true
fi

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }

# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
command -v az >/dev/null 2>&1 || die "Azure CLI (az) not found. Install it first: https://learn.microsoft.com/cli/azure/install-azure-cli"
command -v curl >/dev/null 2>&1 || die "curl not found; it is required for the health check."

az account show >/dev/null 2>&1 || die "Not logged in to Azure. Run 'az login' first, then re-run this script."

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
log "Using subscription: $SUBSCRIPTION_ID"

# ACR names must be globally unique: derive a stable suffix from the subscription id.
SUFFIX="$(echo "$SUBSCRIPTION_ID" | tr -d '-' | tail -c 7)"
ACR_NAME="${ACR_NAME:-ingredionagents${SUFFIX}}"
IMAGE="${ACR_NAME}.azurecr.io/${APP_NAME}:${IMAGE_TAG}"

if [[ "$LIVE_MODE" == "true" ]]; then
  [[ -n "${AZURE_OPENAI_ENDPOINT:-}" ]] || die "--live requires AZURE_OPENAI_ENDPOINT to be set."
  [[ -n "${AZURE_OPENAI_CHAT_DEPLOYMENT:-}" ]] || die "--live requires AZURE_OPENAI_CHAT_DEPLOYMENT to be set."
  log "Live mode: Azure OpenAI calls will use ${AZURE_OPENAI_ENDPOINT}"
else
  log "Offline mode: deterministic demo (no LLM keys needed)."
fi

# --------------------------------------------------------------------------
# 1. Resource group (idempotent)
# --------------------------------------------------------------------------
log "Creating resource group ${RESOURCE_GROUP} in ${LOCATION} ..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# --------------------------------------------------------------------------
# 2. Container registry (idempotent) + build & push the image in Azure
#    (az acr build needs no local Docker daemon)
# --------------------------------------------------------------------------
log "Creating container registry ${ACR_NAME} ..."
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" \
  --sku Basic --admin-enabled false --output none

log "Building and pushing image ${IMAGE} (this takes a few minutes) ..."
az acr build --registry "$ACR_NAME" --image "${APP_NAME}:${IMAGE_TAG}" . --output none

# --------------------------------------------------------------------------
# 3. Container Apps environment (idempotent)
# --------------------------------------------------------------------------
log "Creating Container Apps environment ${ENV_NAME} ..."
az containerapp env create --name "$ENV_NAME" --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" --output none

# --------------------------------------------------------------------------
# 4. Container app: create or update (idempotent)
# --------------------------------------------------------------------------
ENV_VARS="PORT=8000 PYTHONUNBUFFERED=1 GUARDRAILS_STRICTNESS=standard"
if [[ "$LIVE_MODE" == "true" ]]; then
  ENV_VARS="${ENV_VARS} AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT} AZURE_OPENAI_CHAT_DEPLOYMENT=${AZURE_OPENAI_CHAT_DEPLOYMENT}"
fi

if az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  log "Container app exists — updating image and env vars ..."
  az containerapp update --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --image "$IMAGE" --set-env-vars $ENV_VARS --output none
else
  log "Creating container app ${APP_NAME} ..."
  # shellcheck disable=SC2086
  az containerapp create --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$ENV_NAME" --image "$IMAGE" \
    --target-port 8000 --ingress external \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --system-assigned \
    --min-replicas 0 --max-replicas 3 \
    --env-vars $ENV_VARS \
    --output none
fi

# Grant the app's managed identity AcrPull so it can pull the image (idempotent).
PRINCIPAL_ID="$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query identity.principalId -o tsv)"
ACR_ID="$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)"
if [[ -z "$(az role assignment list --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --query '[].id' -o tsv)" ]]; then
  log "Granting AcrPull to the container app identity ..."
  az role assignment create --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --output none
fi

# --------------------------------------------------------------------------
# 5. Wait for the health endpoint, then print the live URL
# --------------------------------------------------------------------------
FQDN="$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)"
HEALTH_URL="https://${FQDN}/api/health"

log "Waiting for ${HEALTH_URL} ..."
for i in $(seq 1 40); do
  if curl -sf --max-time 10 "$HEALTH_URL" >/dev/null 2>&1; then
    log "Service is healthy."
    break
  fi
  if [[ "$i" -eq 40 ]]; then
    die "Health check timed out. Check logs: az containerapp logs show --name $APP_NAME --resource-group $RESOURCE_GROUP"
  fi
  sleep 15
done

echo ""
echo "================================================================"
echo "  Deployed! Demo UI:  https://${FQDN}/"
echo "  API health:        ${HEALTH_URL}"
echo "  API docs:          https://${FQDN}/docs"
echo "================================================================"
echo ""
echo "Teardown (deletes everything this script created):"
echo "  az group delete --name ${RESOURCE_GROUP} --yes --no-wait"
