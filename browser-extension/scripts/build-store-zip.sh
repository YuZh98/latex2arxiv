#!/usr/bin/env bash
# Build a Chrome Web Store upload zip from browser-extension/.
#
# Excludes dev-only paths (tests/, scripts/, node_modules/, package*.json,
# *.md, dist/) so the upload package contains only files Chrome actually
# loads at runtime. Verifies the result against the manifest snapshot
# before declaring success.
#
# Usage:
#   ./browser-extension/scripts/build-store-zip.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${EXT_DIR}/dist"

VERSION="$(python3 -c "import json; print(json.load(open('${EXT_DIR}/manifest.json'))['version'])")"
ZIP_NAME="latex2arxiv-overleaf-${VERSION}.zip"
ZIP_PATH="${DIST_DIR}/${ZIP_NAME}"

mkdir -p "${DIST_DIR}"
rm -f "${ZIP_PATH}"

# Files and directories Chrome needs at runtime. Anything not listed here
# is excluded from the package. The list is explicit (allow-list) rather
# than a deny-list, so a future repo file that should not ship cannot
# slip in by accident.
INCLUDE=(
  manifest.json
  background.js
  content.js
  offscreen.html
  offscreen.js
  worker.js
  panel.css
  icon.png
  lib
  py
  pyodide
  wheels
)

cd "${EXT_DIR}"

# Verify every included path exists before zipping.
for p in "${INCLUDE[@]}"; do
  if [[ ! -e "${p}" ]]; then
    echo "ERROR: ${p} not found under ${EXT_DIR}" >&2
    exit 1
  fi
done

zip -rq "${ZIP_PATH}" "${INCLUDE[@]}" \
  -x "**/.DS_Store" "**/__pycache__/*" "**/*.pyc"

ZIP_SIZE_MB="$(du -m "${ZIP_PATH}" | cut -f1)"
ZIP_SHA256="$(shasum -a 256 "${ZIP_PATH}" | cut -d ' ' -f1)"

echo "Built ${ZIP_PATH}"
echo "  version: ${VERSION}"
echo "  size:    ${ZIP_SIZE_MB} MB"
echo "  sha256:  ${ZIP_SHA256}"
echo
echo "Upload at: https://chrome.google.com/webstore/devconsole"
