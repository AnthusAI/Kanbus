# Contributing to Kanbus

Kanbus is a behavior-specification-first project with two full, independent implementations: Python (`python/`) and Rust (`rust/`). Gherkin scenarios in `features/` are the source of truth, and both implementations must pass the same scenarios with identical observable behavior.

## Set up

See [INSTALL.md](INSTALL.md) for prerequisites. In short:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "python[dev]"
cargo build --manifest-path rust/Cargo.toml
```

## Make a change

1. Pick or file an issue. Kanbus tracks its own work on its own board; run `kbs list --status open` or browse `project/issues`.
2. Branch from `develop`. Pull requests target `develop`, not `main`.
3. Write or extend the Gherkin scenario in `features/` first and watch it fail for the right reason.
4. Implement the change in both Python and Rust so both pass the scenario. A change that is deliberately limited to one implementation needs the `parity-exempt` label and a comment saying why.
5. Run the checks below, then open a pull request.

## Checks

The Rust toolchain files pin only the channel with the minimal profile. Before running the Rust checks, add the components once with `rustup component add rustfmt clippy llvm-tools-preview` (the API service under `services/kanbus-api` needs `rustfmt clippy`).

```bash
make check-python    # black, ruff, behave, pytest, coverage
make check-rust      # cargo fmt, clippy, cargo test, cucumber
make check-parity    # spec and CLI parity between the two implementations
```

Generated documents have to be regenerated when their source changes:

```bash
python tools/generate_configuration_reference.py
python tools/generate_cli_reference.py
```

CI runs `--check` variants of both and fails when a document is stale.

## Style

Python code carries Sphinx docstrings and Rust public items carry doc comments. Prefer long, descriptive names over explanatory comments; comments are for high-level concepts, not for narrating individual lines. The full conventions are in [AGENTS.md](AGENTS.md).

## Working with agents

Coding agents follow [CONTRIBUTING_AGENT.md](CONTRIBUTING_AGENT.md), which is assembled from the methodologies configured in `.kanbus.yml`.

## Security

Do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md).
