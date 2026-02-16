#!/usr/bin/env bash
# Kanbus Symlink Installer
# Creates short symlinks (kbs, kbsc) for kanbus binaries
# Run this after: cargo install kanbusr

set -euo pipefail

echo "Kanbus Shortcut Installer"
echo "========================="
echo ""
echo "This will create the following shortcuts in ~/.cargo/bin/:"
echo "  kbs  -> kanbusr"
echo "  kbsc -> kanbus-console"
echo ""

# Determine cargo bin directory
CARGO_BIN="${CARGO_HOME:-$HOME/.cargo}/bin"

if [[ ! -d "$CARGO_BIN" ]]; then
  echo "Error: Cargo bin directory not found at $CARGO_BIN"
  echo "Please install Rust and cargo first: https://rustup.rs"
  exit 1
fi

# Check if binaries exist
if [[ ! -f "$CARGO_BIN/kanbusr" ]]; then
  echo "Error: kanbusr binary not found at $CARGO_BIN/kanbusr"
  echo "Please run: cargo install kanbusr"
  exit 1
fi

if [[ ! -f "$CARGO_BIN/kanbus-console" ]]; then
  echo "Warning: kanbus-console binary not found at $CARGO_BIN/kanbus-console"
  echo "The console server may not be installed yet."
fi

# Check if symlinks already exist
KBS_EXISTS=false
KBSC_EXISTS=false

if [[ -e "$CARGO_BIN/kbs" ]]; then
  KBS_EXISTS=true
  echo "Note: kbs already exists at $CARGO_BIN/kbs"
fi

if [[ -e "$CARGO_BIN/kbsc" ]]; then
  KBSC_EXISTS=true
  echo "Note: kbsc already exists at $CARGO_BIN/kbsc"
fi

if [[ "$KBS_EXISTS" == "true" && "$KBSC_EXISTS" == "true" ]]; then
  echo ""
  echo "Shortcuts already installed. Nothing to do."
  exit 0
fi

# Prompt for confirmation
echo ""
read -p "Create shortcuts? [Y/n] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Nn]$ ]]; then
  echo "Skipped."
  exit 0
fi

# Create symlinks
if [[ "$KBS_EXISTS" == "false" ]]; then
  ln -sf kanbusr "$CARGO_BIN/kbs"
  echo "✓ Created $CARGO_BIN/kbs -> kanbusr"
fi

if [[ "$KBSC_EXISTS" == "false" && -f "$CARGO_BIN/kanbus-console" ]]; then
  ln -sf kanbus-console "$CARGO_BIN/kbsc"
  echo "✓ Created $CARGO_BIN/kbsc -> kanbus-console"
fi

echo ""
echo "Installation complete! You can now use:"
echo "  kbs --help"
echo "  kbsc"
echo ""
echo "These shortcuts work in all shells (bash, zsh, fish, etc.)"
