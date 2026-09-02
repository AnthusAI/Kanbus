#!/usr/bin/env bash
#
# Cloud Agent install script for Kanbus.
#
# Prepares both implementations (Python and Rust) plus the web console so a
# fresh Cloud Agent can run the CLIs and the realtime console board. The script
# is idempotent and safe to run repeatedly against cached state.
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repository_root}"

# The default base image does not ship the venv seed package, which Python needs
# to create virtual environments. Install it only when it is missing.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3.12-venv
fi

# The default base image pins Rust 1.83, but a transitive dependency requires the
# 2024 edition (stabilized in Rust 1.85). Use the latest stable toolchain.
rustup default stable

# Make the nvm-managed Node toolchain available to this non-interactive shell.
export NVM_DIR="${NVM_DIR:-${HOME}/.nvm}"
if [ -s "${NVM_DIR}/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "${NVM_DIR}/nvm.sh"
fi

# Python implementation: the "kanbus" CLI, installed into a project virtualenv.
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip
pip install -e python
deactivate

# Web console frontend assets (shared UI package plus the console app).
(cd packages/ui && npm install && npm run build)
(cd apps/console && npm install && npm run build)

# Embed the freshly built console assets into the Rust console server so the
# "kbsc" binary serves the board without a separate asset directory.
rm -rf rust/embedded_assets/console
cp -r apps/console/dist rust/embedded_assets/console

# Rust implementation: the "kbs" CLI and the "kbsc" console server.
(cd rust && cargo build --release --bin kbs --bin kbsc)

# Expose kbs and kbsc on PATH via symlinks that auto-update on later rebuilds.
tools/install-system.sh --mode symlink
