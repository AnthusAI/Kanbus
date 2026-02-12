# Index Benchmark Parallel Results

## Goal
Provide a parallel IO variant for index benchmarks to evaluate potential speedups without changing production code paths.

## Summary
- `tools/benchmark_index.py` now reports serial + parallel build/cache timings.
- `rust/src/bin/index_benchmark.rs` now reports serial + parallel build/cache timings.
- Parallel mode uses thread pools to read issue files concurrently, then builds the index sequentially.

## Notes
- Parallel mode is benchmark-only and does not alter Taskulus runtime behavior.
- Serial timings remain the source of truth for performance targets.
