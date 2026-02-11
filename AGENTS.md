<!-- AGENT-SKILL:START project-management-with-beads -->
Use skill at: .agent-skills/project-management-with-beads/SKILL.md
Why: Beads task management is MANDATORY here; every task must live in Beads.
When: Create/update the Beads task before coding; close it only after the change lands.
How: Follow the workflow in the skill for recording, implementation notes, and closure.
<!-- AGENT-SKILL:END project-management-with-beads -->

# Code Quality Standards for Taskulus

## Behavior-Driven Development (BDD)

This project follows a strict outside-in, behavior-driven design approach:

**The specification IS the product.** Every line of production code exists to make a failing Gherkin scenario pass. Write the Gherkin first, watch it fail, then write the minimum code to make it pass.

**Both implementations share the same Gherkin feature files.** Python and Rust are two renderings of the same specification. They must pass the same scenarios.

**100% spec coverage is mandatory.** Every feature must have BDD scenarios. Every scenario must pass in both implementations.

## Code Style Standards

### Python

**Formatting:**
- Use Ruff for linting: `ruff check python/`
- Use Black for formatting: `black python/`
- All files must pass both tools with zero warnings

**Documentation:**
- Sphinx-style docstrings on EVERY class and method
- Format:
  ```python
  def generate_id(title: str, existing_ids: Set[str]) -> str:
      """
      Generate a unique issue ID using SHA256 hash.

      Args:
          title: The issue title to hash
          existing_ids: Set of existing IDs to avoid collisions

      Returns:
          A unique ID string with format 'tsk-{6hex}'

      Raises:
          RuntimeError: If unable to generate unique ID after 10 attempts
      """
  ```

**Naming:**
- Long, clear, descriptive names for everything
- No abbreviations: `generate_issue_identifier()` not `gen_id()`
- Use full words: `configuration` not `config` (except in file names)

**Comments:**
- NO line-level comments that duplicate the code
- Only block-level comments for higher-level context
- Code should be self-documenting through clear names

**Type Hints:**
- Use type hints on all function signatures
- Use dataclasses with type annotations for data structures

### Rust

**Formatting:**
- Use clippy: `cargo clippy -- -D warnings` (fail on warnings)
- Use rustfmt: `cargo fmt --check`
- All files must pass both tools

**Documentation:**
- Doc comments on EVERY public struct, enum, function, and method
- Use `///` for item docs and `//!` for module docs
- Format:
  ```rust
  /// Generate a unique issue ID using SHA256 hash.
  ///
  /// # Arguments
  /// * `title` - The issue title to hash
  /// * `existing_ids` - Set of existing IDs to avoid collisions
  ///
  /// # Returns
  /// A unique ID string with format 'tsk-{6hex}'
  ///
  /// # Errors
  /// Returns `TaskulusError::IdGenerationFailed` if unable to generate unique ID after 10 attempts
  pub fn generate_id(title: &str, existing_ids: &HashSet<String>) -> Result<String, TaskulusError>
  ```

**Naming:**
- Use Rust naming conventions (snake_case for functions, PascalCase for types)
- But still favor clarity: `generate_issue_identifier()` over `gen_id()`

**Comments:**
- Same policy as Python: no line-level comments duplicating code
- Only block-level comments for higher-level context

**Error Handling:**
- Use `Result<T, E>` and `?` operator
- Custom error types with context

## Spec Parity Requirements

**Critical:** Python and Rust implementations must produce identical behavior for the same inputs.

**JSON serialization parity:**
- Same key ordering
- Same timestamp format (RFC3339)
- Same pretty-printing (2-space indents)
- Test with byte-for-byte comparison

**Error message parity:**
- Same error messages for same failure conditions
- Same exit codes

**CLI output parity:**
- Same formatting
- Same order of output

## Quality Gates (All Must Pass)

Before any PR can merge:

1. **Format verification**
   - `black --check python/` ✓
   - `ruff check python/` ✓
   - `cargo fmt --check` ✓
   - `cargo clippy -- -D warnings` ✓

2. **Documentation verification**
   - All Python functions have Sphinx docstrings ✓
   - All Rust public items have doc comments ✓

3. **Spec parity verification**
   - `tools/check_spec_parity.py` passes ✓
   - No step definitions exist in only one implementation

4. **Behavior specs**
   - `pytest` passes (all Gherkin scenarios pass) ✓
   - `cargo test` passes (all Gherkin scenarios pass) ✓

5. **Coverage**
   - Python coverage ≥ 100% (pytest-cov) ✓
   - Rust coverage ≥ 100% (cargo-tarpaulin) ✓

6. **YAML test cases** (when implemented)
   - Both implementations pass identical YAML test vectors ✓

## Workflow for Implementing Features

1. **Write Gherkin scenarios first** in `specs/features/`
2. **Verify both test runners can parse them** (scenarios will be pending/skipped)
3. **Implement Python step definitions** in `python/tests/step_definitions/`
4. **Implement Python production code** to make scenarios pass
5. **Implement Rust step definitions** in `rust/tests/step_definitions/`
6. **Implement Rust production code** to make scenarios pass
7. **Run parity checker** to verify both implementations are in sync
8. **Run all quality gates**
9. **Submit PR only when all gates pass**

## Milestones

**M1 (Minimal Viable Tracker):** Can create, show, update, close, delete issues (Epic 6 complete)

**M2 (Usable for Planning):** Can query, filter, search issues (Epic 9 complete)

**M3 (Self-Hosting):** Wiki system works, can use Taskulus to track Taskulus (Epic 11 complete)

**M4 (1.0 Release):** All features complete, migration works, documentation complete (Epic 17 complete)

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
