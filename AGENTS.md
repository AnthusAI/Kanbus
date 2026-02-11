<!-- AGENT-SKILL:START project-management-with-beads -->
Use skill at: .agent-skills/project-management-with-beads/SKILL.md
Why: Beads task management is MANDATORY here; every task must live in Beads.
When: Create/update the Beads task before coding; close it only after the change lands.
How: Follow the workflow in the skill for recording, implementation notes, and closure.
<!-- AGENT-SKILL:END project-management-with-beads -->

# CRITICAL PROJECT POLICY: NO EMOJIS

**ZERO TOLERANCE: No emojis anywhere in this project.**

This applies to:
- Code (comments, docstrings, error messages)
- Documentation (README, guides, specs, wiki pages)
- Git commit messages
- Beads task titles and descriptions
- CLI output
- Test scenarios and step definitions

Use clear, professional text instead. Emojis reduce clarity and professionalism.

# Code Quality Standards for Taskulus

## Behavior-Driven Development (BDD)

This project follows a strict outside-in, behavior-driven design approach:

**The specification IS the product.** Every line of production code exists to make a failing Gherkin scenario pass. Write the Gherkin first, watch it fail, then write the minimum code to make it pass.

**Both implementations share the same Gherkin feature files.** Python and Rust are two renderings of the same specification. They must pass the same scenarios.

**100% spec coverage is mandatory.** Every feature must have BDD scenarios. Every scenario must pass in both implementations.

**Specification completeness:** Every behavior that exists must be specified. If a behavior cannot be specified clearly, it should not exist (remove it or make it a hard error).

## CRITICAL: No Backward Compatibility or Fallback Logic

**This is a strict, non-negotiable policy across the entire Taskulus project:**

- **NO backward compatibility code**: Never preserve old code paths when updating to a new approach
- **NO fallback logic**: Never check multiple locations or try alternative approaches
- **NO "support both ways"**: There is ONE correct way, implement that way only
- **NO legacy support**: Old structures are upgraded through migration, not supported forever
- **ONE way to do things**: If there's a new metadata location, use ONLY that location

**Why this matters:**
- Fallback logic creates exponential complexity
- Multiple code paths mean multiple failure modes
- Backward compatibility prevents evolution
- "Just in case" code becomes permanent debt

**What to do instead:**
- Implement the current, correct approach cleanly
- If old data exists, fail gracefully with clear error messages
- Document migration paths separately (don't mix with runtime code)
- Use the migration epic (Epic 14) for structured data migration

**Examples of what NOT to do:**
```python
# WRONG - trying both locations with fallback
try:
    config = load_from_new_location()
except:
    try:
        config = load_from_old_location()  # NO! Don't do this!
    except:
        config = default_config()
```

**Examples of what TO do:**
```python
# RIGHT - one location, clear error
try:
    config = load_configuration_from_project_directory()
except FileNotFoundError as error:
    raise ConfigurationError(
        "No config.yaml found in project/ directory. "
        "Run 'tsk init' to initialize a new project."
    ) from error
```

## Code Style Standards

### Python

**Formatting:**
- Use Ruff for linting: `ruff check python/`
- Use Black for formatting: `black python/`
- All files must pass both tools with zero warnings

**Documentation:**
- Sphinx-style docstrings are REQUIRED for all public functions, classes, and modules
- Use reStructuredText field lists (`:param`, `:type`, `:return`, `:rtype`, `:raises`)
- Format:
  ```python
  from typing import Set
  from pydantic import BaseModel, Field

  class IssueIdentifierRequest(BaseModel):
      """
      Request to generate a unique issue identifier.

      :param title: The issue title to hash.
      :type title: str
      :param existing_ids: Set of existing IDs to avoid collisions.
      :type existing_ids: Set[str]
      """
      title: str = Field(min_length=1)
      existing_ids: Set[str] = Field(default_factory=set)

  def generate_issue_identifier(request: IssueIdentifierRequest) -> str:
      """
      Generate a unique issue ID using SHA256 hash.

      :param request: Validated request containing title and existing IDs.
      :type request: IssueIdentifierRequest
      :return: A unique ID string with format 'tsk-{6hex}'.
      :rtype: str
      :raises RuntimeError: If unable to generate unique ID after 10 attempts.
      """
      # Implementation here
      pass
  ```

**Naming:**
- Long, clear, descriptive names for everything
- No abbreviations: `generate_issue_identifier()` not `gen_id()`
- Use full words: `configuration` not `config` (except in file names)
- Invest more tokens in clear names than in implementation

**Comments:**
- NO line-level comments. Comments create drift and obscure clarity.
- Block comments ONLY when capturing high-level ideas or rationale
- No step-by-step narration
- Code should be self-documenting through clear names and small, readable functions

**Type Hints:**
- Use type hints on all function signatures
- Use Pydantic models at boundaries (configurations, APIs, CLI output)
- Validation errors must be converted to clear, user-facing messages

**Domain Modeling:**
- Use Pydantic models whenever data crosses a boundary
- Clear validation with helpful error messages

### Rust

**Formatting:**
- Use clippy: `cargo clippy -- -D warnings` (fail on warnings)
- Use rustfmt: `cargo fmt --check`
- All files must pass both tools with zero warnings

**Documentation:**
- Rustdoc comments are REQUIRED on EVERY public struct, enum, function, and method
- Use `///` for item docs and `//!` for module docs
- Format mirrors Python Sphinx style:
  ```rust
  use serde::{Deserialize, Serialize};
  use std::collections::HashSet;

  /// Request to generate a unique issue identifier.
  ///
  /// # Fields
  /// * `title` - The issue title to hash
  /// * `existing_ids` - Set of existing IDs to avoid collisions
  #[derive(Debug, Clone, Serialize, Deserialize)]
  pub struct IssueIdentifierRequest {
      pub title: String,
      #[serde(default)]
      pub existing_ids: HashSet<String>,
  }

  /// Generate a unique issue ID using SHA256 hash.
  ///
  /// # Arguments
  /// * `request` - Validated request containing title and existing IDs
  ///
  /// # Returns
  /// A unique ID string with format 'tsk-{6hex}'
  ///
  /// # Errors
  /// Returns `TaskulusError::IdGenerationFailed` if unable to generate unique ID after 10 attempts
  pub fn generate_issue_identifier(
      request: &IssueIdentifierRequest,
  ) -> Result<String, TaskulusError> {
      // Implementation here
      todo!()
  }
  ```

**Naming:**
- Use Rust naming conventions (snake_case for functions, PascalCase for types)
- But still favor clarity: `generate_issue_identifier()` over `gen_id()`
- Long, descriptive names (no abbreviations)
- Invest more tokens in clear names than in implementation

**Comments:**
- NO line-level comments. Comments create drift and obscure clarity.
- Block comments ONLY when capturing high-level ideas or rationale
- No step-by-step narration
- Code should be self-documenting through clear names and small, readable functions

**Error Handling:**
- Use `Result<T, E>` and `?` operator
- Custom error types with context and clear messages
- Error messages must match Python implementation exactly

**Domain Modeling:**
- Use serde-based structs for data at boundaries
- Validation should produce clear, user-facing error messages

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
