## Project management with Kanbus

Use Kanbus for task management.
Why: Kanbus task management is MANDATORY here; every task must live in Kanbus.
When: Create/update the Kanbus task before coding; close it only after the change lands.
How: See CONTRIBUTING_AGENT.md for the Kanbus workflow, hierarchy, status rules, priorities, command examples, and the sins to avoid. Never inspect project/ or issue JSON directly (including with cat or jq); use Kanbus commands only.
Performance: Prefer kanbusr (Rust) when available; kanbus (Python) is equivalent but slower.
Warning: Editing project/ directly is a sin against The Way. Do not read or write anything in project/; work only through Kanbus.

# CRITICAL PROJECT POLICY: NO EMOJIS

**ZERO TOLERANCE: No emojis anywhere in this project.**

This applies to:
- Code (comments, docstrings, error messages)
- Documentation (README, guides, specs, wiki pages)
- Git commit messages
- Kanbus issue titles and descriptions
- CLI output
- Test scenarios and step definitions

Use clear, professional text instead. Emojis reduce clarity and professionalism.

## CRITICAL: No Backward Compatibility or Fallback Logic

**This is a strict, non-negotiable policy across the entire Kanbus project:**

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
        "Run 'kanbus init' to initialize a new project."
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
      :return: A unique ID string with format 'kanbus-{6hex}'.
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
  /// A unique ID string with format 'kanbus-{6hex}'
  ///
  /// # Errors
  /// Returns `KanbusError::IdGenerationFailed` if unable to generate unique ID after 10 attempts
  pub fn generate_issue_identifier(
      request: &IssueIdentifierRequest,
  ) -> Result<String, KanbusError> {
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
   - `behave` passes (all Gherkin scenarios pass) ✓
   - `cargo test` passes (all Gherkin scenarios pass) ✓

5. **Coverage**
   - Python coverage ≥ 100% ✓
   - Rust coverage ≥ 100% (cargo-tarpaulin) ✓

6. **YAML test cases** (when implemented)
   - Both implementations pass identical YAML test vectors ✓

## Workflow for Implementing Features

1. **Write Gherkin scenarios first** in `features/`
2. **Verify both test runners can parse them** (scenarios will be pending/skipped)
3. **Implement Python step definitions** in `python/features/steps/`
4. **Implement Python production code** to make scenarios pass
5. **Implement Rust step definitions** in `rust/tests/step_definitions/`
6. **Implement Rust production code** to make scenarios pass
7. **Run parity checker** to verify both implementations are in sync
8. **Run all quality gates**
9. **Submit PR only when all gates pass**


