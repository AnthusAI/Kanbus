# Recursive Project Discovery Benchmarks

## Goal
Measure the latency impact of recursive project discovery versus a single-project workspace. Benchmarks should be reproducible and use deterministic fixture data.

## Scenarios

### Scenario A: Single project (baseline)
- Working directory: `<fixtures_root>/single`
- Layout:
  - `single/project/issues/*.json`
- Dataset size: 1 project, 200 issues (default).
- Intended operations:
  - Discovery: `discover_project_directories` on the working directory.
  - Listing: `kanbus list` end-to-end execution time.
  - Ready query: `kanbus ready` end-to-end execution time.
  - Parallel mode: load issues per project concurrently and report timings alongside serial runs.

### Scenario B: Multi-project recursive discovery
- Working directory: `<fixtures_root>/multi`
- Layout:
  - `multi/services/service-01/project/issues/*.json`
  - `multi/services/service-02/project/issues/*.json`
  - ...
  - `multi/services/service-10/project/issues/*.json`
- Dataset size: 10 projects, 200 issues per project (default).
- Intended operations:
  - Discovery: `discover_project_directories` on the monorepo root.
  - Listing: `kanbus list` end-to-end execution time.
  - Ready query: `kanbus ready` end-to-end execution time.
  - Parallel mode: load issues per project concurrently and report timings alongside serial runs.

## Fixture Generation
Fixtures are generated with deterministic timestamps and issue identifiers.

Command:
```
python tools/benchmark_discovery_fixtures.py \
  --root tools/tmp/benchmark-discovery-fixtures \
  --projects 10 \
  --issues-per-project 200
```

Expected output:
- `tools/tmp/benchmark-discovery-fixtures/single/project/issues/*.json`
- `tools/tmp/benchmark-discovery-fixtures/multi/services/service-*/project/issues/*.json`

## Determinism
- Fixed timestamp: `2026-02-11T00:00:00Z`
- Identifiers: `kanbus-{project:02d}{issue:04d}`
- Titles: `Project {project} issue {issue}`

## Notes
- Fixture generation does not run automatically in CI.
- Benchmarks should read the fixture root and avoid modifying files in place.
