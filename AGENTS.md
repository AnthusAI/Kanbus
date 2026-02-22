## Project management with Kanbus

Use Kanbus for task management.
Why: Kanbus task management is MANDATORY here; every task must live in Kanbus.
When: Create/update the Kanbus task before coding; close it only after the change lands.
How: See CONTRIBUTING_AGENT.md for the Kanbus workflow, hierarchy, status rules, priorities, command examples, and the sins to avoid. Never inspect project/ or issue JSON directly (including with cat or jq); use Kanbus commands only.
Performance: Prefer kanbusr (Rust) when available; kanbus (Python) is equivalent but slower.
Warning: Editing project/ directly is a sin against The Way. Do not read or write anything in project/; work only through Kanbus.

## System-wide kbs/kbsc install (agent PATH)

The agent environment only sees `/usr/local/bin` by default. To ensure `kbs` and `kbsc` are always available without PATH hacks, use the repo helper:

```bash
tools/install-system.sh
```

To avoid reinstalling after every build, use a one-time system-wide symlink:

```bash
tools/install-system.sh --mode symlink
```

This may require sudo once to create the links in `/usr/local/bin`. After that, rebuild with `cargo build --release` and the symlinks will pick up the new binaries automatically.

## VideoML pipeline (Kanb.us)

The Kanb.us marketing site uses VideoML sources in `videos/`. The render and upload flow is centralized in root scripts.

Required environment variables:
- `VIDEOML_CLI` path to the VideoML CLI entry (e.g., `/path/to/videoml/cli/bin/vml.js`)
- `BABULUS_BUNDLE` path to the Babulus standard bundle JS

Local render + preview:
```bash
node scripts/render-videos.js
```
This bundles custom components, generates timelines, renders the intro MP4, and copies MP4/JPG assets into `apps/kanb.us/static/videos` for local preview. To preview on the Gatsby site, set:
```
GATSBY_VIDEOS_BASE_URL=/videos
```

Upload to CDN:
```bash
VIDEOS_BUCKET=<bucket-name> VIDEOS_PREFIX=videos node scripts/upload-videos.js
```
The upload script requires `VIDEOS_BUCKET` and `VIDEOS_PREFIX` and syncs MP4/JPG assets to S3. There is no fallback logic.

## Console UI Control

When the user is actively watching the Kanbus console UI (typically at http://localhost:4242), you can programmatically control the interface to guide their attention. These commands use real-time socket+SSE notifications with sub-100ms latency.

### Available Commands

**Focus on an issue** - Immediately highlights an issue and opens it in the detail panel, filtering the board to show only that issue and its descendants:
```bash
kbs console focus <issue-id>
```

**Reload the page** - Triggers an immediate page reload in the browser, useful after frontend changes:
```bash
kbs console reload
```

This enables self-iteration on frontend issues: after rebuilding the frontend (`cd apps/console && npm run build`), use `kbs console reload` to instantly test changes without manual browser refresh.

### When to Use UI Control

Use `kbs console focus` proactively when:
- **After creating important issues**: Direct attention to new epics or critical tasks
- **After significant updates**: Show the user changes you've made
- **During collaborative work**: Coordinate by showing what you're working on
- **To provide context**: Help the user understand relationships between issues

### Example Workflows

After creating a new epic with sub-tasks:
```bash
kbs create "Implement authentication" --type epic
# Creates tskl-abc
kbs create "Add login form" --parent tskl-abc --type task
kbs create "Add JWT tokens" --parent tskl-abc --type task
kbs console focus tskl-abc  # Show the epic and all sub-tasks
```

When starting work on a task:
```bash
kbs update tskl-xyz --status in_progress --assignee agent
kbs console focus tskl-xyz  # Show what you're working on
```

After completing a complex change:
```bash
kbs close tskl-xyz
kbs console focus tskl-abc  # Show the parent epic with updated status
```

### Future Commands (tskl-m59)

Additional UI control commands are planned but not yet implemented:
- `kbs console unfocus` - Clear focus filter
- `kbs console view <initiatives|epics|issues>` - Switch view modes
- `kbs console search <query>` - Set search query
- `kbs console maximize` - Maximize detail panel
- `kbs console close-detail` - Close detail panel
- `kbs console settings mode <light|dark>` - Control appearance
- `kbs console column collapse <name>` - Collapse board columns

Check `kbs show tskl-m59` for implementation status.

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

## Rust coverage (repeatable command)

Use this command to get the library/test coverage figure (excludes binaries and test harness targets) that matches our usual badge number:

```bash
PATH="$HOME/.cargo/bin:$PATH" \
cargo llvm-cov report \
  --manifest-path rust/Cargo.toml \
  --ignore-filename-regex 'rust/src/bin/.*|rust/tests/.*'
```

The last run with this filter reported **87.30% line coverage**. Always use the same ignore regex to keep the denominator consistent. If you need HTML output, add `--html --output-dir /tmp/kanbus-cov-lib` to the same command.

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
   - Rust coverage ≥ 100% (cargo llvm-cov) ✓

## Rust Coverage (Local)

**Required toolchain:**
```bash
rustup component add llvm-tools-preview
cargo install cargo-llvm-cov --locked
```

**Console assets (required for `embed-assets`):**
```bash
(cd packages/ui && npm ci && npm run build)
(cd apps/console && npm ci && npm run build)
rm -rf rust/embedded_assets/console
cp -R apps/console/dist rust/embedded_assets/console
```

**Coverage run:**
```bash
cd rust
mkdir -p ../coverage-rust
cargo llvm-cov --locked --no-report --all-features --lib --bins --tests --ignore-filename-regex "features/steps/.*|src/bin/.*|src/main.rs"
cargo llvm-cov report --locked --cobertura --output-path ../coverage-rust/cobertura.xml
```

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

## Git Flow Standards

This project follows a standard Git Flow workflow:

-   **`main`**: Stable, production-ready code. Direct commits are restricted.
-   **`dev`**: The integration branch for new features. All feature branches target `dev`.
-   **Feature Branches**: Create from `dev` (e.g., `feature/my-cool-feature`). Merge back to `dev` via PR.
-   **Releases**: When `dev` is stable, merge `dev` -> `main`.
-   **Hotfixes**: Critical fixes may branch from `main` (e.g., `hotfix/urgent-fix`) and merge to both `main` and `dev`.

**Agent Protocol:**
-   Always check which branch you are on (`git status`).
-   If implementing a feature, ensure you branch from `dev`.
-   If asked to switch branches, preserve uncommitted changes unless instructed otherwise.
