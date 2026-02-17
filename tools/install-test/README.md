# Installation Smoke Tests (Manual)

Purpose: verify that the released artifacts install and can list issues using:
- PyPI package `kanbus` (CLI `kanbus`)
- crates.io package `kanbus` (binaries `kbs` / `kbsc`)
- Optional comparison between Python and Rust outputs

These tests run in Amazon Linux containers and do **not** touch the source tree. Run them manually (not in CI) after a release.

## PyPI smoke (kanbus)
```bash
docker build -f tools/install-test/Dockerfile.python -t kanbus-pypi-smoke .
docker run --rm kanbus-pypi-smoke
```

## Crates smoke (kbs) + cross-check against Python
```bash
docker build -f tools/install-test/Dockerfile.rust -t kanbus-crate-smoke .
docker run --rm kanbus-crate-smoke
```

Both containers create a fresh temp project, add three sample issues, and list them. The Rust smoke also diffs Rust vs Python outputs to ensure parity.

Note: These tests fetch released artifacts from PyPI/crates.io; they do not use the local repo contents and are safe to run from anywhere.
