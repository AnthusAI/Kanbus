#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
kanbusr_bin=${1:-"${repo_root}/dist/kanbusr"}
console_bin=${2:-"${repo_root}/dist/kanbus-console"}

kanbusr_bin=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$kanbusr_bin")
console_bin=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$console_bin")
dist_dir=$(python3 -c 'import os,sys; print(os.path.dirname(os.path.realpath(sys.argv[1])))' "$kanbusr_bin")

if [[ ! -f "$kanbusr_bin" ]]; then
  echo "kanbusr binary not found at $kanbusr_bin" >&2
  exit 1
fi
if [[ ! -f "$console_bin" ]]; then
  echo "console server binary not found at $console_bin" >&2
  exit 1
fi

work_dir=$(mktemp -d)
cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT

mkdir -p "$work_dir/project"
cp -R "$repo_root/apps/console/tests/fixtures/project"/* "$work_dir/project/"
cat > "$work_dir/.kanbus.yml" <<'YAML'
project_directory: project
project_key: kanbus
YAML

chmod +x "$kanbusr_bin" "$console_bin"

docker run --rm \
  -v "$work_dir":/data \
  -v "$dist_dir":/dist \
  ubuntu:24.04 \
  bash -lc '
    set -euo pipefail
    apt-get update -y >/dev/null
    apt-get install -y curl >/dev/null
    ls -la /dist
    /dist/kanbusr --version

    # Test embedded assets (NO CONSOLE_ASSETS_ROOT)
    CONSOLE_DATA_ROOT=/data CONSOLE_PORT=5174 /dist/kanbus-console >/tmp/console.log 2>&1 &
    server_pid=$!

    for _ in $(seq 1 30); do
      if curl -sf http://127.0.0.1:5174/api/config >/dev/null; then
        break
      fi
      sleep 0.5
    done

    # Verify API works
    curl -sf http://127.0.0.1:5174/api/issues >/dev/null

    # Verify frontend loads
    curl -sf http://127.0.0.1:5174/ | grep -q "<!doctype html"

    # Verify JS assets load
    asset_path=$(curl -sf http://127.0.0.1:5174/ | grep -oP "assets/index-[^\"]+\.js" | head -1)
    if [ -n "$asset_path" ]; then
      curl -sf "http://127.0.0.1:5174/$asset_path" >/dev/null
    fi

    # Verify startup message shows embedded assets
    grep -q "embedded assets" /tmp/console.log

    kill "$server_pid"
  '
