# Kanbus Coverage Policy (March 6, 2026)

## Baseline

Coverage ratchet baseline is frozen in `config/coverage-baselines.json`:

- `python_line_coverage: 80.5`
- `rust_line_coverage: 65.0`
- `max_gap_points: 15.5`

Baselines only move via explicit `--update-baseline`.

## CI Enforcement

CI generates both artifacts and enforces ratchet rules:

- Python: `coverage-python/coverage.xml`
  - `coverage run --source=kanbus -m pytest`
  - `KANBUS_ENABLE_COVERAGE_HELPER=0 coverage run --append --source=kanbus -m behave`
- Rust: `coverage-rust/cobertura.xml`
  - `cargo llvm-cov --all-features --lib --bins --tests`

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
