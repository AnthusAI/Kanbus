#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
crate_dir="${root_dir}/rust"

usage() {
  cat <<'EOF'
Usage: tools/install-system.sh [--prefix <dir>] [--mode {install|symlink}] [--bin {kbs|kbsc|both}]

Defaults:
  --prefix /usr/local
  --mode   install   (cargo install to prefix)
  --bin    both      (install kbs and kbsc)

Examples:
  tools/install-system.sh
  tools/install-system.sh --prefix /opt/homebrew
  tools/install-system.sh --mode symlink --prefix /usr/local
  tools/install-system.sh --bin kbs
EOF
}

prefix="/usr/local"
mode="install"
bins="both"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      prefix="${2:-}"
      shift 2
      ;;
    --mode)
      mode="${2:-}"
      shift 2
      ;;
    --bin)
      bins="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$bins" != "kbs" && "$bins" != "kbsc" && "$bins" != "both" ]]; then
  echo "Invalid --bin value: $bins" >&2
  exit 1
fi

if [[ "$mode" != "install" && "$mode" != "symlink" ]]; then
  echo "Invalid --mode value: $mode" >&2
  exit 1
fi

bin_args=()
if [[ "$bins" == "kbs" || "$bins" == "both" ]]; then
  bin_args+=(--bin kbs)
fi
if [[ "$bins" == "kbsc" || "$bins" == "both" ]]; then
  bin_args+=(--bin kbsc)
fi

if [[ "$mode" == "install" ]]; then
  cmd=(cargo install --path "${crate_dir}" --root "${prefix}" --force)
  cmd+=("${bin_args[@]}")
  if [[ -w "${prefix}/bin" ]]; then
    "${cmd[@]}"
  else
    sudo "${cmd[@]}"
  fi
  exit 0
fi

mkdir -p "${crate_dir}/target/release"
if [[ "$bins" == "kbs" || "$bins" == "both" ]]; then
  cargo build --manifest-path "${crate_dir}/Cargo.toml" --bin kbs --release
fi
if [[ "$bins" == "kbsc" || "$bins" == "both" ]]; then
  cargo build --manifest-path "${crate_dir}/Cargo.toml" --bin kbsc --release
fi

link_dir="${prefix}/bin"
if [[ -w "${link_dir}" ]]; then
  sudo_needed=""
else
  sudo_needed="sudo"
fi

if [[ "$bins" == "kbs" || "$bins" == "both" ]]; then
  ${sudo_needed} ln -sf "${crate_dir}/target/release/kbs" "${link_dir}/kbs"
fi
if [[ "$bins" == "kbsc" || "$bins" == "both" ]]; then
  ${sudo_needed} ln -sf "${crate_dir}/target/release/kbsc" "${link_dir}/kbsc"
fi
