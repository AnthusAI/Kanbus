# Kanbus Coverage Policy (March 9, 2026)

## Baseline

Coverage ratchet baseline is frozen in `config/coverage-baselines.json`:

- `python_line_coverage: 79.41`
- `rust_line_coverage: 78.1616`
- `max_gap_points: 1.2484`

Baselines only move via explicit `--update-baseline`.

## CI Enforcement

CI generates both artifacts and enforces ratchet rules:

- Python: `coverage-python/coverage.xml`
  - `coverage run --source=kanbus -m pytest`
  - `KANBUS_ENABLE_COVERAGE_HELPER=0 coverage run --append --source=kanbus -m behave --tags "~wip"`
- Rust: `coverage-rust/cobertura.xml`
  - `KANBUS_CUCUMBER_INCLUDE_CONSOLE=1 cargo llvm-cov --all-features --lib --bins --tests`

Blocking gate:

```bash
python tools/coverage_ratchet.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --baseline-file config/coverage-baselines.json
```

Machine-readable output for CI annotations:

```bash
python tools/coverage_ratchet.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --baseline-file config/coverage-baselines.json \
  --json
```

Changed-files gate (PR and push):

```bash
python tools/coverage_changed_files_gate.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --config config/coverage-changed-files.json \
  --base-ref <base-ref> \
  --head-ref <head-ref>
```

## Rust Console Parity Gate

Rust has a dedicated console parity lane:

```bash
cd rust
KANBUS_CUCUMBER_ONLY_CONSOLE=1 cargo test --locked --test cucumber -- --fail-fast
```

## Coverage Delta Reporting

Use this report to identify shared-module parity gaps:

```bash
python tools/coverage_parity_report.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --limit 25
```

## Coverage Uplift Status Log

Last updated: March 9, 2026 (`feature/coverage-uplift`).

Recent pushed checkpoints:

- `5b59914` `test(py): complete ai summarize branch coverage`
- `551f09a` `test(rust): expand beads write helper branch coverage`
- `ffafecd` `test(rust): deepen gossip helper and uds branch coverage`
- `bcb03f6` `test(rust): expand snyk sync helper coverage`
- `69a667c` `test(py): drive snyk sync module to full targeted coverage`
- `4f278d9` `test(py): drive overlay module to full targeted coverage`
- `1f4f104` `test(py): drive gossip module to full targeted coverage`

Local validation snapshots run during these checkpoints:

- Rust targeted lanes:
  - `cd rust && cargo test --locked --lib gossip`
  - `cd rust && cargo test --locked --lib beads_write`
  - `cd rust && cargo test --locked --lib snyk_sync`
- Python targeted lanes:
  - `conda run -n py311 pytest -q python/tests/test_ai_summarize.py`
  - `pytest -q python/tests/test_overlay.py`
  - `pytest -q python/tests/test_snyk_sync.py`
- Cross-language gate:
  - `conda run -n py311 python tools/coverage_ratchet.py --python-xml coverage-python/coverage.xml --rust-xml coverage-rust/cobertura.xml --baseline-file config/coverage-baselines.json`
  - Result at last run: `python_line_coverage=79.41`, `rust_line_coverage=78.16`, `status=passing`.

Known resume points:

- Re-generate fresh combined coverage artifacts before next ratchet bump so new tests are reflected in `coverage-python/coverage.xml` and `coverage-rust/cobertura.xml`.
- Next largest remaining uplift targets:
  - Python: `cli.py`, `beads_write.py`, `console_snapshot.py`, `console_ui_state.py`
  - Rust: `overlay.rs`, `beads_write.rs`, `gossip.rs`, `console_local.rs`, `console_lambda.rs`
