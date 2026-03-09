# Rust Coverage

## Source of Truth

Rust coverage is generated with `cargo llvm-cov` and exported as Cobertura XML:

- `coverage-rust/cobertura.xml`

Python coverage is generated at:

- `coverage-python/coverage.xml`

Both artifacts are required by the cross-language ratchet gate.

## Ratchet Policy

Coverage is enforced against `config/coverage-baselines.json`.

Frozen baseline (March 9, 2026):

- `python_line_coverage: 78.82`
- `rust_line_coverage: 68.0329`
- `max_gap_points: 10.7871`

Rules:

- Python line coverage must not regress below baseline.
- Rust line coverage must not regress below baseline.
- Python minus Rust gap must not exceed `max_gap_points`.

Run gate locally:

```bash
python tools/coverage_ratchet.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --baseline-file config/coverage-baselines.json
```

Intentional baseline update:

```bash
python tools/coverage_ratchet.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --baseline-file config/coverage-baselines.json \
  --update-baseline
```

## Rust Coverage Command

```bash
cd rust
mkdir -p ../coverage-rust
KANBUS_CUCUMBER_INCLUDE_CONSOLE=1 cargo llvm-cov --locked --no-report --all-features --lib --bins --tests --ignore-filename-regex "features/steps/.*"
cargo llvm-cov report --locked --cobertura --output-path ../coverage-rust/cobertura.xml
```

## Console Assets Requirement

Because coverage runs with `--all-features`, embedded console assets must exist:

```bash
(cd packages/ui && npm ci && npm run build)
(cd apps/console && npm ci && npm run build)
rm -rf rust/embedded_assets/console
cp -R apps/console/dist rust/embedded_assets/console
```

## Rust Console Parity Lane

Dedicated `@console` behavior lane:

```bash
cd rust
KANBUS_CUCUMBER_ONLY_CONSOLE=1 cargo test --locked --test cucumber -- --fail-fast
```

This lane is separate from UI Playwright tests and is meant to keep Rust step behavior in sync for console-tagged specs.

## Coverage Delta Report

```bash
python tools/coverage_parity_report.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --limit 25
```

## Changed-Files Gate

CI also enforces changed-file coverage floors:

```bash
python tools/coverage_changed_files_gate.py \
  --python-xml coverage-python/coverage.xml \
  --rust-xml coverage-rust/cobertura.xml \
  --config config/coverage-changed-files.json \
  --base-ref <base-ref> \
  --head-ref <head-ref>
```
