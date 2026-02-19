# Kanbus Test Coverage Report (Feb 19, 2026)

## Rust
- Runner: `CARGO_TARGET_DIR=/tmp/kanbus-target cargo test --test cucumber -- --fail-fast`.
- Latest run: **0 failures**, **40 skipped** (dependency interop Given steps still skipped). All executed scenarios passed. Full suite (non fail-fast) still pending.
- Coverage: tarpaulin not run tonight; functional parity verified for executed scenarios.

## Python
- Runner sequence (coverage combined):
  - `coverage run -m pytest python/tests`
  - `coverage run -a -m behave`
  - `coverage xml`
- Latest results: **528/528 scenarios passing** (0 skipped) + 4 pytest unit tests.
- Coverage with `.coveragerc`: **99% line coverage** (coverage.xml at repo root). Remaining misses: `python/src/kanbusr/__init__.py` (3 stub lines).

## Release gate (tonight)
- Temporary threshold: **95% overall**. Python now meets it (99%); Rust scenarios green for fail-fast run. Decide if a full Rust suite run is required before release.

## Next actions
1) Run full Rust cucumber suite (without `--fail-fast`) to confirm no hidden failures.
2) If desired, add a tiny test for `kanbusr/__init__.py` or mark it as vendor/omit to hit 100% Python.
3) Consider unskipping dependency interop Given steps to remove skips and align with spec.
