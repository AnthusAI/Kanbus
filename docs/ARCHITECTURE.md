# Architecture Overview

Taskulus is intentionally simple: a git-backed issue store with dual Python and Rust implementations that share a single specification. The architecture keeps storage, execution, and user experience aligned so both runtimes behave identically.

## Language Duality

Taskulus ships two first-class CLIs—Python and Rust—that execute the same Gherkin-defined behaviors. The Python path is optimized for rapid iteration and rich ecosystem tooling; the Rust path is optimized for binary distribution and tight resource use. Both consume the same project layout, data model, and validation rules to preserve behavioral parity.

## File Organization Model

Taskulus stores each issue as its own JSON file under `project/issues/`, eliminating merge-heavy monoliths and removing any secondary database. Hierarchical types and workflows live in `project/config.yaml`, keeping schema alongside data. There is exactly one storage path: the JSON files in the repository. No fallbacks, no mirrored SQLite caches, and no daemon-owned state are required to read or list issues.

## Performance Benchmark

We benchmarked end-to-end “list all beads” latency using the Beads project itself as real-world data:

- Dataset: cloned `beads` repository into `tmp/beads`, normalized `.beads/issues.jsonl`, and converted 836 issues into `project/issues/*.json`.
- Commands (5 runs each, cache cleared between runs): `bd --no-daemon list`; `python -m taskulus.cli --beads list`; `tskr --beads list`; `python -m taskulus.cli list`; `tskr list`.
- Metric: wall-clock time from process start to completed output.

The results show that fast listing does not require a SQLite sidecar. Taskulus streams directly from JSON files while matching or beating the SQLite-backed Beads path, removing an entire class of synchronization failures and simplifying the mental model for operators and contributors.

![Beads CLI Listing Latency](images/beads_cli_benchmark.png)

Median timings (ms) for convenience:
- Beads (Go, SQLite + JSONL): 173.4
- Taskulus Python — Beads JSONL: 499.3
- Taskulus Rust — Beads JSONL: 9.8 (first cold run was higher; median reflects steady state)
- Taskulus Python — Project JSON: 643.0
- Taskulus Rust — Project JSON: 73.6

Takeaway: Removing the SQLite layer eliminates sync complexity and improves portability without sacrificing speed for the core listing workflow.
