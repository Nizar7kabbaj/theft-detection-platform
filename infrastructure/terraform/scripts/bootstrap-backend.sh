#!/usr/bin/env bash

set -euo pipefail

LOCATION="${LOCATION:-francecentral}"
RG_NAME="${RG_NAME:-rg-tfstate-theft}"
SA_NAME="${SA_NAME:-sttfstatetheft}"
CONTAINER_NAME="${CONTAINER_NAME:-tfstate}"

PROJECT_TAG="theft-detection"
ENV_TAG="shared"
MANAGED_BY_TAG="bootstrap-script"

echo "==> az account context"
az account show --query '{name:name, id:id, tenantId:tenantId}' -o table

echo "==> checking storage account name availability"
AVAILABLE=$(az storage account check-name --name "$SA_NAME" --query nameAvailable -o tsv)
if [[ "$AVAILABLE" != "true" ]]; then
    OWNED=$(az storage account list --query "[?name=='$SA_NAME'].id" -o tsv)
    if [[ -z "$OWNED" ]]; then
        echo "ERROR: name '$SA_NAME' is taken in another subscription."
        echo "       Pick a new name and re-run with: SA_NAME=<new> $0"
        exit 1
    fi
    echo "   exists in this subscription — idempotent re-run path"
fi

echo "==> ensuring resource group '$RG_NAME' in $LOCATION"
az group create \
    --name "$RG_NAME" \
    --location "$LOCATION" \
    --tags project="$PROJECT_TAG" environment="$ENV_TAG" managed_by="$MANAGED_BY_TAG" \
    -o none

echo "==> ensuring storage account '$SA_NAME'"
if ! az storage account show -n "$SA_NAME" -g "$RG_NAME" -o none 2>/dev/null; then
    az storage account create \
        --name "$SA_NAME" \
        --resource-group "$RG_NAME" \
        --location "$LOCATION" \
        --sku Standard_LRS \
        --kind StorageV2 \
        --min-tls-version TLS1_2 \
        --allow-blob-public-access false \
        --public-network-access Enabled \
        --tags project="$PROJECT_TAG" environment="$ENV_TAG" managed_by="$MANAGED_BY_TAG" \
        -o none
    echo "   created"
else
    echo "   exists — re-applying hardening"
    az storage account update \
        --name "$SA_NAME" \
        --resource-group "$RG_NAME" \
        --min-tls-version TLS1_2 \
        --allow-blob-public-access false \
        -o none
fi

echo "==> enabling blob versioning and 7-day soft delete"
az storage account blob-service-properties update \
    --account-name "$SA_NAME" \
    --resource-group "$RG_NAME" \
    --enable-versioning true \
    --enable-delete-retention true \
    --delete-retention-days 7 \
    --enable-container-delete-retention true \
    --container-delete-retention-days 7 \
    -o none

echo "==> granting current user 'Storage Blob Data Contributor' on the SA"
CURRENT_USER_OID=$(az ad signed-in-user show --query id -o tsv)
SA_ID=$(az storage account show -n "$SA_NAME" -g "$RG_NAME" --query id -o tsv)

EXISTING=$(az role assignment list \
    --assignee "$CURRENT_USER_OID" \
    --scope "$SA_ID" \
    --role "Storage Blob Data Contributor" \
    --query "[].id" -o tsv)
if [[ -z "$EXISTING" ]]; then
    az role assignment create \
        --assignee "$CURRENT_USER_OID" \
        --role "Storage Blob Data Contributor" \
        --scope "$SA_ID" \
        -o none
    echo "   assigned — sleeping 30s for AAD propagation"
    sleep 30
else
    echo "   already assigned"
fi

echo "==> ensuring blob container '$CONTAINER_NAME'"
EXISTS=$(az storage container exists \
    --account-name "$SA_NAME" \
    --name "$CONTAINER_NAME" \
    --auth-mode login \
    --query exists -o tsv)
if [[ "$EXISTS" != "true" ]]; then
    az storage container create \
        --account-name "$SA_NAME" \
        --name "$CONTAINER_NAME" \
        --auth-mode login \
        --public-access off \
        -o none
    echo "   created"
else
    echo "   exists"
fi

echo "==> disabling shared-key access (AAD-only)"
az storage account update \
    --name "$SA_NAME" \
    --resource-group "$RG_NAME" \
    --allow-shared-key-access false \
    -o none

echo ""
echo "============================================================"
echo "Backend ready."
echo ""
echo "  resource_group_name  = \"$RG_NAME\""
echo "  storage_account_name = \"$SA_NAME\""
echo "  container_name       = \"$CONTAINER_NAME\""
echo "  location             = \"$LOCATION\""
echo ""
echo "Wire these into environments/<env>/backend.tf with a per-env"
echo "key (e.g. key = \"dev.tfstate\")."
echo "============================================================"
