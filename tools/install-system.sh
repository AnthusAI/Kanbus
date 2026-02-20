#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
crate_dir="${root_dir}/rust"

# Default to the first writable bin directory in PATH that is a standard
# system location, so the installed binaries appear before any user-local
# copies (e.g. ~/.cargo/bin) that might shadow them.
detect_prefix() {
  local candidates=(/opt/homebrew /usr/local)
  for candidate in "${candidates[@]}"; do
    if [[ -d "${candidate}/bin" ]]; then
      echo "${candidate}"
      return
    fi
  done
  echo "/usr/local"
}

usage() {
  cat <<'EOF'
Usage: tools/install-system.sh [--prefix <dir>] [--mode {install|symlink}] [--bin {kbs|kbsc|both}]

Defaults:
  --prefix  auto-detected (/opt/homebrew on Apple Silicon, /usr/local elsewhere)
  --mode    symlink   (build release binary and symlink from prefix/bin)
  --bin     both      (install kbs and kbsc)

Modes:
  symlink  Build a release binary and create a symlink in prefix/bin. Subsequent
           cargo build --release runs auto-update the commands without re-running
           this script.

  install  Run cargo install into prefix. Does not auto-update on rebuild.

Both modes scan PATH and remove any other copies of the installed binaries that
would shadow the canonical installation.

Examples:
  tools/install-system.sh
  tools/install-system.sh --prefix /usr/local
  tools/install-system.sh --mode install
  tools/install-system.sh --bin kbs
EOF
}

prefix="$(detect_prefix)"
mode="symlink"
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

bin_names=()
bin_args=()
if [[ "$bins" == "kbs" || "$bins" == "both" ]]; then
  bin_names+=(kbs)
  bin_args+=(--bin kbs)
fi
if [[ "$bins" == "kbsc" || "$bins" == "both" ]]; then
  bin_names+=(kbsc)
  bin_args+=(--bin kbsc)
fi

link_dir="${prefix}/bin"
if [[ -w "${link_dir}" ]]; then
  sudo_cmd=""
else
  sudo_cmd="sudo"
fi

# Remove any copies of the binaries from PATH directories other than the
# installation target, so nothing shadows the canonical installation.
remove_shadowing_copies() {
  local IFS=":"
  for dir in $PATH; do
    [[ "$dir" == "${link_dir}" ]] && continue
    for name in "${bin_names[@]}"; do
      local target="${dir}/${name}"
      if [[ -e "$target" || -L "$target" ]]; then
        echo "Removing shadowing copy at ${target}"
        if [[ -w "${dir}" ]]; then
          rm -f "${target}"
        else
          sudo rm -f "${target}"
        fi
      fi
    done
  done
}

if [[ "$mode" == "install" ]]; then
  cmd=(cargo install --path "${crate_dir}" --root "${prefix}" --force)
  cmd+=("${bin_args[@]}")
  ${sudo_cmd} "${cmd[@]}"
  remove_shadowing_copies
  exit 0
fi

cargo build --manifest-path "${crate_dir}/Cargo.toml" --release "${bin_args[@]}"

for name in "${bin_names[@]}"; do
  ${sudo_cmd} ln -sf "${crate_dir}/target/release/${name}" "${link_dir}/${name}"
  echo "Symlinked ${link_dir}/${name} -> ${crate_dir}/target/release/${name}"
done

remove_shadowing_copies
