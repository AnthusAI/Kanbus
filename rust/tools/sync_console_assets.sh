#!/usr/bin/env bash
set -euo pipefail

# Rebuild console assets and copy into rust/embedded_assets/console
# so that cargo builds with embed-assets can succeed locally.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

pushd "$ROOT_DIR/apps/console" >/dev/null
npm ci
npm run build
popd >/dev/null

rm -rf "$ROOT_DIR/rust/embedded_assets/console"
cp -R "$ROOT_DIR/apps/console/dist" "$ROOT_DIR/rust/embedded_assets/console"

echo "Synced console assets into rust/embedded_assets/console"
