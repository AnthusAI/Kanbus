# Installation

This repository contains two implementations of Taskulus: Python and Rust. Both use the same Gherkin specs.

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
tsk --version
tsk doctor
```

Note: the `tsk` console script is available when the virtual environment is active.

## Rust (developer install)

```bash
cd rust
cargo build
```

Run the CLI:

```bash
./target/debug/tskr --version
./target/debug/tskr doctor
```

## Verify

```bash
make check-python
make check-rust
```

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
| macOS (local) | Verified | Verified | `tsk --version` and `tsk doctor` run in temp repo |
| Linux | Pending | Pending | Needs validation |
| Windows | Pending | Pending | Needs validation |
