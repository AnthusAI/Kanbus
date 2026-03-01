# Policy Guardrails + Kairotic Guidance Implementation Summary

## Status (Verified March 1, 2026)
`tskl-zz1` implementation is complete and verified in both runtimes.

This completion includes:
- policy guardrails (blocking enforcement),
- kairotic guidance (timely warning/suggestion coaching),
- list-level and ready-level guidance hooks,
- policy CLI extensions,
- website/docs updates including explicit kairos framing.

## Delivered scope

### Policy DSL and evaluator
- Added guidance-capable policy steps in Python and Rust:
  - `Then warn "TEXT"`
  - `Then suggest "TEXT"`
  - `Then explain "TEXT"` (attachment semantics)
  - `When viewing an issue`
  - `When updating an issue`
  - `When deleting an issue`
  - `When listing issues`
  - `When listing ready issues`
  - `Then the issue must have at least N child issues`
- Added dual-mode evaluation model:
  - enforcement mode (blocking)
  - guidance mode (non-blocking)
- Added structured report output:
  - violations + guidance items with severity, source file/scenario/step, and explanations.
- Enforced orphan `explain` validation.

### Runtime behavior and hooks
- Guidance hooks now run after successful:
  - `show`, `create`, `update`, `close`, `delete`, `list`, `ready`.
- List-level guidance cadence is every invocation (unless suppressed).
- Guidance output is emitted on `stderr` using:
  - `GUIDANCE WARNING: ...`
  - `GUIDANCE SUGGESTION: ...`
  - indented `Explanation: ...`
- Added suppression controls:
  - global `--no-guidance`
  - `KANBUS_NO_GUIDANCE=1`

### CLI commands
- Added `kanbus policy guide <identifier>`.
- Extended/verified:
  - `kanbus policy list`
  - `kanbus policy validate`
  - `kanbus policy check`

### Epic-ready guardrail + coaching
- Implemented policy support for:
  - blocking epic -> `ready` when child count is below threshold.
- Added/verified guidance messaging for this rule:
  - why epics require decomposition into child issues,
  - warning/suggestion lines,
  - attached explanations.

### Docs and feature pages
- Updated:
  - `apps/kanb.us/src/content/features.ts`
  - `apps/kanb.us/src/pages/features/policy-as-code.tsx`
  - `apps/kanb.us/src/pages/docs/features/policy-as-code.tsx`
  - `apps/kanb.us/src/components/FeaturePictogram.tsx`
- Added explicit kairos positioning and guidance narrative.
- Replaced policy pictogram with road-sign style guidance/warning/error animation and reduced-motion fallback.

## Verification evidence (March 1, 2026)

### Policy-focused verification
- Command:
  - `conda run -n py311 bash -lc 'cd python && behave ../features/policies'`
- Result:
  - `7 features passed, 0 failed, 0 skipped`
  - `41 scenarios passed, 0 failed, 0 skipped`
  - `295 steps passed, 0 failed, 0 skipped`

- Command:
  - `cd rust && cargo test --test cucumber -- --name 'Policy|policy|guidance|ready'`
- Result:
  - `[Summary] 10 features`
  - `[Summary] 28 scenarios (28 passed)`
  - `[Summary] 191 steps (191 passed)`

Policy acceptance for active policy suite:
- `features/policies/*` are passing with no failed or skipped scenarios in both runtimes.

### Full quality gates
- Command:
  - `conda run -n py311 bash -lc 'cd python && black --check . && ruff check . && behave'`
- Result:
  - `All checks passed!`
  - `77 features passed, 0 failed, 0 skipped`
  - `686 scenarios passed, 0 failed, 5 skipped`
  - `3602 steps passed, 0 failed, 24 skipped`

- Command:
  - `cd rust && cargo fmt --check && cargo clippy -- -D warnings && cargo test`
- Result:
  - `cargo fmt --check`: pass
  - `cargo clippy -- -D warnings`: pass
  - `cargo test`: exit code `0`
  - `[Summary] 70 features`
  - `[Summary] 650 scenarios (648 passed, 2 skipped)`
  - `[Summary] 3420 steps (3418 passed, 2 skipped)`

## Notes
- Console notification/socket warnings observed during tests are non-blocking in this environment and did not affect pass/fail outcomes.
- This document supersedes earlier stale status text and is the current auditable record for `tskl-zz1` completion verification on March 1, 2026.
