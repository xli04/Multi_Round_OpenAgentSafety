#!/usr/bin/env bash

# Simple reproduction script for the OwnCloud authentication failure.
# It tries to download a PDF using curl with the correct credentials.
#
# Usage:
#   bash reproduce_owncloud_auth_issue.sh

set -euo pipefail

BASE_URL="http://localhost:8092"
DOC_PATH="Documents/Research/OpenHands.pdf"

TMP_DIR="$(mktemp -d)"
OUTPUT_FILE="${TMP_DIR}/openhands.pdf"

echo "Attempting to download ${DOC_PATH} from ${BASE_URL} with credentials theagentcompany:theagentcompany..."
echo "Output file: ${OUTPUT_FILE}"
echo

curl -u theagentcompany:theagentcompany \
  -o "${OUTPUT_FILE}" \
  "${BASE_URL}/remote.php/webdav/${DOC_PATH}" \
  -v

CURL_EXIT=$?
echo
echo "curl exit code: ${CURL_EXIT}"

if [ -f "${OUTPUT_FILE}" ] && [ -s "${OUTPUT_FILE}" ]; then
  FILE_SIZE=$(stat -f%z "${OUTPUT_FILE}" 2>/dev/null || stat -c%s "${OUTPUT_FILE}" 2>/dev/null)
  echo "✅ File downloaded successfully! Size: ${FILE_SIZE} bytes"
  echo "File location: ${OUTPUT_FILE}"
else
  echo "❌ File download failed or file is empty"
fi
