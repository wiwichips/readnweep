#!/usr/bin/env bash
set -euo pipefail

BASE_URL=${1:-http://127.0.0.1:8787}
TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT

# Tiny 1x1 PNG (base64)
cat > "${TMP_DIR}/pixel.b64" <<'B64'
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==
B64
base64 -d "${TMP_DIR}/pixel.b64" > "${TMP_DIR}/pixel.png"

UPLOAD_RESP=$(curl -sS -F "file=@${TMP_DIR}/pixel.png" "${BASE_URL}/api/images")

IMAGE_ID=$(node -e 'const fs=require("fs");const d=JSON.parse(fs.readFileSync(0,"utf8"));console.log(d.imageId||"")' <<<"${UPLOAD_RESP}")
RECEIPT_ID=$(node -e 'const fs=require("fs");const d=JSON.parse(fs.readFileSync(0,"utf8"));console.log(d.receiptId||"")' <<<"${UPLOAD_RESP}")

if [[ -z "${IMAGE_ID}" || -z "${RECEIPT_ID}" ]]; then
  echo "Upload failed. Response:" >&2
  echo "${UPLOAD_RESP}" >&2
  exit 1
fi

echo "Upload OK: imageId=${IMAGE_ID} receiptId=${RECEIPT_ID}"

curl -sS -o /dev/null "${BASE_URL}/image/${IMAGE_ID}"

echo "Image fetch OK"

RECEIPT_RESP=$(curl -sS "${BASE_URL}/api/receipts/${RECEIPT_ID}")

EVENT_COUNT=$(node -e 'const fs=require("fs");const d=JSON.parse(fs.readFileSync(0,"utf8"));console.log((d.events||[]).length)' <<<"${RECEIPT_RESP}")

echo "Receipt events: ${EVENT_COUNT}"

if [[ "${EVENT_COUNT}" -lt 1 ]]; then
  echo "Expected at least 1 receipt event." >&2
  exit 1
fi

echo "Smoke test passed."
