#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a; source "$ROOT/.env"; set +a

SUFFIX="${FOUNDRY_RESOURCE_NAME##*-}"
LOCATION="${LOCATION:-swedencentral}"
STORAGE="rippleiqst${SUFFIX}"
APP="rippleiq-engine-${SUFFIX}"

if ! az storage account show -n "$STORAGE" -g "$RESOURCE_GROUP" -o none 2>/dev/null; then
    echo ">>> Creating storage account $STORAGE"
    az storage account create -n "$STORAGE" -g "$RESOURCE_GROUP" -l "$LOCATION" --sku Standard_LRS \
        --allow-blob-public-access false -o none
fi

if ! az functionapp show -n "$APP" -g "$RESOURCE_GROUP" -o none 2>/dev/null; then
    echo ">>> Creating Flex Consumption function app $APP"
    az functionapp create -n "$APP" -g "$RESOURCE_GROUP" --storage-account "$STORAGE" \
        --flexconsumption-location "$LOCATION" --runtime python --runtime-version 3.12 \
        --instance-memory 2048 -o none
fi

echo ">>> Packaging engine"
BUILD="$(mktemp -d)"
cp "$ROOT"/api/function_app.py "$ROOT"/api/host.json "$ROOT"/api/requirements.txt "$BUILD"/
cp "$ROOT"/engine.py "$ROOT"/service.py "$BUILD"/
mkdir -p "$BUILD/data" && cp "$ROOT"/data/*.json "$BUILD/data/"
(cd "$BUILD" && zip -qr app.zip .)

echo ">>> Deploying (remote build)"
az functionapp deployment source config-zip -n "$APP" -g "$RESOURCE_GROUP" --src "$BUILD/app.zip" --build-remote true -o none

URL="https://$(az functionapp show -n "$APP" -g "$RESOURCE_GROUP" --query properties.defaultHostName -o tsv)/api"
grep -q "^RIPPLEIQ_API_URL=" "$ROOT/.env" && sed -i '' "s#^RIPPLEIQ_API_URL=.*#RIPPLEIQ_API_URL=$URL#" "$ROOT/.env" || echo "RIPPLEIQ_API_URL=$URL" >> "$ROOT/.env"
echo ">>> Engine API: $URL"
curl -s "$URL/health"; echo
