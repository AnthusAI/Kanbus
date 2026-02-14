# Installation

This repository contains two implementations of Kanbus: Python and Rust. Both use the same Gherkin specs.

## Prerequisites

- Git
- Python 3.11+
- Rust toolchain (stable)

## Python (developer install)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e python
```

Run the CLI:

```bash
kanbus --version
kanbus doctor
```

Note: the `kanbus` console script is available when the virtual environment is active.

## Rust (developer install)

```bash
cd rust
cargo build
```

Run the CLI:

```bash
./target/debug/kanbusr --version
./target/debug/kanbusr doctor
```

## Verify

```bash
make check-python
make check-rust
```

## Beads interoperability suite

This is a full integration check that uses the real Beads CLI and the real Beads repository data.

Prerequisites:
- Beads CLI (`bd`) installed and on PATH
- Go toolchain (for CI builds of Beads, not required if you use an existing `bd` binary)

Run locally:

```bash
python tools/build_rust_release.py
python tools/run_beads_interop_suite.py --bd-binary "$(command -v bd)" --rust-binary rust/target/release/kanbusr
```

CI runs this suite in the `beads-interop` job after the standard quality gates.

## CI publish (semantic-release + crates.io)

Semantic-release runs in `python/` and creates version tags. The release workflow then:
1. Builds and uploads Python to PyPI (semantic-release).
2. Syncs `rust/Cargo.toml` version to the semantic-release tag.
3. Publishes the Rust crate from `rust/`.

Rust publish guardrails:
- Steps: `cargo fmt --check`, `cargo clippy --locked -- -D warnings`, `cargo test --locked`, `cargo package --locked`, `cargo publish --locked`.
- Requires repository secret `CARGO_REGISTRY_TOKEN`.

## Platform status

| Platform | Python install | Rust release build | Notes |
|----------|----------------|--------------------|-------|
| macOS (local) | Verified | Verified | `kanbus --version` and `kanbus doctor` run in temp repo |
| Linux | Pending | Pending | Needs validation |
| Windows | Pending | Pending | Needs validation |
