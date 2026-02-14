# Kanbus Implementation Plan

## Preamble: The Governing Philosophy

This plan is written from the perspective of outside-in, behavior-driven design. Every line of production code exists to make a failing specification pass. Every specification exists because a user behavior demands it. We write the Gherkin first, watch it fail, then write the minimum code to make it pass -- in both Python and Rust, against the same specification.

The spec suite is not a test suite. It is the product. The Python and Rust implementations are two renderings of the same specification.

---

## Part 1: Directory Structure

### The Problem

The VISION.md proposes a conventional split: `python/`, `rust/`, and `specs/` as top-level siblings. This works, but it creates cognitive distance between a behavior specification and the code that implements it. When working on the workflow state machine, you want the Gherkin scenarios, the Python step definitions, and the Rust step definitions all within reach -- not scattered across three directory trees.

However, we must respect real constraints:
- Python requires `pyproject.toml` at the package root with a `src/` layout
- Rust requires `Cargo.toml` at the crate root with a `src/` layout
- Gherkin feature files must be locatable by both `behave` and `cucumber-rs`
- The shared YAML test cases from the vision must also live somewhere accessible to both runners

### The Recommended Layout

```
Kanbus/
    planning/
        VISION.md
        IMPLEMENTATION_PLAN.md

    specs/                                  # THE SOURCE OF TRUTH
        features/                           # Shared Gherkin feature files
            initialization/
                project_initialization.feature
            issues/
                issue_creation.feature
                issue_update.feature
                issue_deletion.feature
                issue_display.feature
            workflow/
                status_transitions.feature
                automatic_side_effects.feature
                claim_workflow.feature
            hierarchy/
                parent_child_validation.feature
                reparenting.feature
            dependencies/
                blocked_by_dependencies.feature
                relates_to_dependencies.feature
                cycle_detection.feature
                ready_query.feature
            queries/
                list_filtering.feature
                search.feature
                blocked_listing.feature
            comments/
                add_comment.feature
            wiki/
                wiki_rendering.feature
                wiki_template_functions.feature
                wiki_listing.feature
            maintenance/
                validation.feature
                statistics.feature
            index/
                index_building.feature
                cache_invalidation.feature
        test-cases/                         # YAML-driven test case directories
            issue-crud/                     # (structure as specified in VISION.md)
                create-basic/
                    test.yaml
                    input/
                        kanbus.yml
                ...
        fixtures/                           # Reusable input fixtures
            default_config.yaml
            config_with_epic_workflow.yaml
            sample_issues/
                open_task.json
                closed_task.json
                blocked_task.json
                epic_with_children.json
                ...

    python/                                 # Python implementation
        pyproject.toml
        src/
            kanbus/
                __init__.py
                cli.py
                models.py
                index.py
                wiki.py
                workflows.py
                hierarchy.py
                dependencies.py
                ids.py
                file_io.py
                config.py
                queries.py
                cache.py
        features/
            environment.py                  # Behave hooks, sys.path setup
            steps/                          # Step definitions organized by domain
                common_steps.py             # Given steps: project setup, issue exists, etc.
                initialization_steps.py
                issue_crud_steps.py
                workflow_steps.py
                hierarchy_steps.py
                dependency_steps.py
                query_steps.py
                comment_steps.py
                wiki_steps.py
                maintenance_steps.py
                index_steps.py
            features/                      # Shared Gherkin specs
        tests/
            features/                       # behave feature runner configuration
            spec_runner/                    # YAML test-case runner
                __init__.py
                runner.py
            unit/                           # Python-specific unit tests (edge cases)
                __init__.py
                test_id_generation.py
                test_cache_serialization.py

    rust/                                   # Rust implementation
        Cargo.toml
        src/
            main.rs
            cli.rs
            models.rs
            index.rs
            wiki.rs
            workflows.rs
            hierarchy.rs
            dependencies.rs
            ids.rs
            file_io.rs
            config.rs
            queries.rs
            cache.rs
            lib.rs                          # Library root for testability
        tests/
            features/                       # Symlink -> ../../features/
            step_definitions/
                mod.rs
                common_steps.rs
                initialization_steps.rs
                issue_crud_steps.rs
                workflow_steps.rs
                hierarchy_steps.rs
                dependency_steps.rs
                query_steps.rs
                comment_steps.rs
                wiki_steps.rs
                maintenance_steps.rs
                index_steps.rs
            spec_runner/
                mod.rs
                runner.rs                   # YAML test-case runner
            cucumber.rs                     # cucumber-rs main entry
            unit/
                mod.rs
                test_id_generation.rs
                test_cache_serialization.rs

    tools/                                  # Build and quality tooling
        check_spec_parity.py                # Verify both impls cover all scenarios
        check_feature_coverage.py           # Verify all features have step defs
        ci/
            quality_gates.sh                # Master script for CI
            python_checks.sh
            rust_checks.sh

    .github/
        workflows/
            ci.yml                          # GitHub Actions CI pipeline

    Makefile                                # Convenience targets for local dev
    AGENTS.md
```

### Key Design Decisions in This Layout

**Feature files live in `features/`, period.** Both implementations reference this single source of truth. Python's Behave runner points at `python/behave.ini` (a path to `../../features/`). Rust's `tests/features/` is a path to `../../features/`. One set of Gherkin, two implementations.

**Step definitions mirror each other.** `python/tests/step_definitions/workflow_steps.py` and `rust/tests/step_definitions/workflow_steps.rs` implement the same Given/When/Then steps for the same feature files. A developer working on workflows opens three files: the feature, the Python steps, and the Rust steps. Parallel structure makes comparison trivial.

**YAML test cases are a separate, complementary mechanism.** The Gherkin features describe behavior in human-readable scenarios. The YAML test cases (from the vision) provide data-driven test vectors. Both are valuable. The Gherkin drives the design conversation; the YAML cases provide exhaustive coverage of edge cases.

**The `tools/` directory holds cross-cutting quality scripts.** The parity checker, coverage checker, and CI orchestration live here because they span both implementations.

**Symlinks for Rust feature access.** Rust's cucumber-rs expects features relative to the crate. A path (`rust/tests/features/ -> ../../features/`) is the cleanest solution. On Windows (if ever needed), a build script can copy the features directory.

---

## Part 2: Epic and Task Breakdown

### Epic 0: Repository Bootstrap

**Goal:** A developer can clone the repo, run a single command, and have both toolchains ready with all quality gates passing on an empty codebase.

#### Task 0.1: Repository skeleton and build configuration

**Gherkin:** None (infrastructure, not behavior).

**Python:**
- `pyproject.toml` with dependencies: click, jinja2, pyyaml, behave, ruff, black, sphinx
- `src/kanbus/__init__.py` with version string
- Empty test suite that passes

**Rust:**
- `Cargo.toml` with dependencies: clap, serde, serde_json, serde_yaml, minijinja, sha2, cucumber, etc.
- `src/main.rs` and `src/lib.rs` stubs
- Empty test suite that passes

**Quality gates:**
- `ruff check python/` passes
- `black --check python/` passes
- `cargo clippy` passes with no warnings
- `cargo fmt --check` passes
- `behave` passes (0 scenarios, 0 failures)
- `behave` passes (0 scenarios, 0 failures)
- `cargo test` passes (0 tests, 0 failures)

**Deliverables:**
- Makefile with targets: `make check-python`, `make check-rust`, `make check-all`, `make fmt`
- `.github/workflows/ci.yml` running all quality gates on every push
- `.gitignore` covering Python, Rust, and the project `.cache/` directory

#### Task 0.2: Shared fixtures directory and feature file skeleton

**Gherkin:** Stub feature files for every domain with `@wip` tags and placeholder scenarios.

**Python:** `behave.ini` configured to find `features/`.

**Rust:** Symlink created. `cucumber.rs` configured to find features via the path.

**Quality gates:** Both test runners can discover feature files (even if all scenarios are pending/skipped).

---

### Epic 1: Project Initialization (`kanbus init`)

**Goal:** A user can run `kanbus init` in a git repository and get a properly structured project directory.

**Dependencies:** Epic 0.

#### Task 1.1: Write Gherkin scenarios for `kanbus init`

Write `features/initialization/project_initialization.feature`:

```gherkin
Feature: Project initialization
    As a developer starting a new project
    I want to initialize a Kanbus project directory
    So that I can begin tracking issues alongside my code

    Scenario: Initialize with default settings
        Given an empty git repository
        When I run "kanbus init"
        Then a ".kanbus.yml" file should exist in the repository root
        And a "project" directory should exist
        And a "kanbus.yml" file should exist with default configuration
        And a "project/issues" directory should exist and be empty
        And a "project/wiki" directory should exist
        And a "project/wiki/index.md" file should exist
        And a "project/.cache" directory should not exist yet

    Scenario: Initialize with custom directory name
        Given an empty git repository
        When I run "kanbus init --dir tracking"
        Then a ".kanbus.yml" file should exist pointing to "tracking"
        And a "tracking" directory should exist
        And a "tracking/kanbus.yml" file should exist with default configuration

    Scenario: Refuse to initialize when project already exists
        Given a git repository with an existing Kanbus project
        When I run "kanbus init"
        Then the command should fail with exit code 1
        And stderr should contain "already initialized"

    Scenario: Refuse to initialize outside a git repository
        Given a directory that is not a git repository
        When I run "kanbus init"
        Then the command should fail with exit code 1
        And stderr should contain "not a git repository"
```

**Quality gate:** Both behave and cucumber-rs can parse and report these scenarios as pending.

#### Task 1.2: Implement `kanbus init` in Python

**Implementation:**
- `config.py`: `DefaultConfiguration` class that produces the default `kanbus.yml` content
- `file_io.py`: Functions to write YAML, create directories, detect git repositories
- `cli.py`: Click command group with `init` subcommand

**Quality gates:**
- All four scenarios pass in behave
- `ruff check` clean
- `black --check` clean
- Every class and public function has a Sphinx docstring

#### Task 1.3: Implement `kanbus init` in Rust

**Implementation:**
- `config.rs`: `DefaultConfiguration` struct with serialization
- `file_io.rs`: Functions to write YAML, create directories, detect git repositories
- `cli.rs`: Clap command with `init` subcommand

**Quality gates:**
- All four scenarios pass in cucumber-rs
- `cargo clippy` clean (deny warnings)
- `cargo fmt --check` clean
- Every public item has a `///` doc comment

#### Task 1.4: Write YAML test cases for `kanbus init`

Data-driven tests covering: default init, custom directory, already-initialized, not-a-repo.

---

### Epic 2: Data Model and Configuration

**Goal:** Both implementations can parse `kanbus.yml`, represent issues as typed structures, and serialize/deserialize issue JSON files with identical behavior.

**Dependencies:** Epic 1 (needs config file to exist).

#### Task 2.1: Write Gherkin scenarios for configuration parsing

`features/configuration/configuration_loading.feature`:

```gherkin
Feature: Configuration loading
    As the Kanbus system
    I need to load and validate project configuration
    So that all operations use consistent type, workflow, and hierarchy rules

    Scenario: Load default configuration
        Given a Kanbus project with default configuration
        When the configuration is loaded
        Then the prefix should be "kanbus"
        And the hierarchy should be "initiative, epic, task, sub-task"
        And the non-hierarchical types should be "bug, story, chore"
        And the initial status should be "open"
        And the default priority should be 2

    Scenario: Reject configuration with unknown fields
        ...

    Scenario: Reject configuration with empty hierarchy
        ...

    Scenario: Reject configuration with duplicate type names
        ...
```

#### Task 2.2: Implement data models in Python

**Implementation:**
- `models.py`:
  - `IssueData` dataclass (all fields from the spec)
  - `DependencyLink` dataclass (`target`, `dependency_type`)
  - `IssueComment` dataclass (`author`, `text`, `created_at`)
  - `ProjectConfiguration` dataclass (parsed from `kanbus.yml`)
  - `WorkflowDefinition` dataclass (state machine graph)
- `config.py`:
  - `load_project_configuration(path) -> ProjectConfiguration`
  - `validate_project_configuration(config) -> list[str]` (returns validation errors)
- `file_io.py`:
  - `read_issue_from_file(path) -> IssueData`
  - `write_issue_to_file(issue, path)`
  - JSON serialization: pretty-printed, 2-space indent, sorted keys for determinism

**Quality gates:** Scenarios pass. All types have docstrings. Ruff/Black clean.

#### Task 2.3: Implement data models in Rust

**Implementation:**
- `models.rs`:
  - `IssueData` struct with `#[derive(Serialize, Deserialize, Debug, Clone)]`
  - `DependencyLink` struct
  - `IssueComment` struct
  - `ProjectConfiguration` struct
  - `WorkflowDefinition` struct
- `config.rs`:
  - `load_project_configuration(path) -> Result<ProjectConfiguration>`
  - `validate_project_configuration(config) -> Vec<String>`
- `file_io.rs`:
  - `read_issue_from_file(path) -> Result<IssueData>`
  - `write_issue_to_file(issue, path) -> Result<()>`

**Quality gates:** Scenarios pass. All public items documented. Clippy/rustfmt clean.

#### Task 2.4: ID generation

`features/issues/id_generation.feature`:

```gherkin
Feature: Issue ID generation
    Scenario: Generated IDs follow the prefix-hex format
        Given a project with prefix "kanbus"
        When I generate an issue ID
        Then the ID should match the pattern "kanbus-[0-9a-f]{6}"

    Scenario: Generated IDs are unique across multiple creations
        Given a project with prefix "kanbus"
        When I generate 100 issue IDs
        Then all 100 IDs should be unique

    Scenario: ID generation handles collision with existing issues
        Given a project with an existing issue "kanbus-aaaaaa"
        And the hash function would produce "aaaaaa" for the next issue
        When I generate an issue ID
        Then the ID should not be "kanbus-aaaaaa"
        And the ID should match the pattern "kanbus-[0-9a-f]{6}"
```

Implement `ids.py` and `ids.rs`. Both use SHA256 of `title + timestamp + random bytes`, take first 6 hex chars, retry on collision.

---

### Epic 3: Workflow State Machine

**Goal:** Status transitions are validated against the workflow graph defined in configuration.

**Dependencies:** Epic 2 (needs models and config).

#### Task 3.1: Write Gherkin scenarios for workflow transitions

`features/workflow/status_transitions.feature`:

```gherkin
Feature: Workflow status transitions
    As a project manager
    I want status transitions to follow defined workflows
    So that issues move through a predictable lifecycle

    Scenario Outline: Valid transitions in default workflow
        Given a Kanbus project with default configuration
        And an issue "kanbus-test01" of type "task" with status "<from_status>"
        When I run "kanbus update kanbus-test01 --status <to_status>"
        Then the command should succeed
        And issue "kanbus-test01" should have status "<to_status>"

        Examples:
            | from_status | to_status   |
            | open        | in_progress |
            | open        | closed      |
            | open        | deferred    |
            | in_progress | open        |
            | in_progress | blocked     |
            | in_progress | closed      |
            | blocked     | in_progress |
            | blocked     | closed      |
            | closed      | open        |
            | deferred    | open        |
            | deferred    | closed      |

    Scenario Outline: Invalid transitions in default workflow
        Given a Kanbus project with default configuration
        And an issue "kanbus-test01" of type "task" with status "<from_status>"
        When I run "kanbus update kanbus-test01 --status <to_status>"
        Then the command should fail with exit code 1
        And stderr should contain "invalid transition"
        And issue "kanbus-test01" should have status "<from_status>"

        Examples:
            | from_status | to_status   |
            | open        | blocked     |
            | blocked     | open        |
            | blocked     | deferred    |
            | closed      | in_progress |
            | closed      | blocked     |
            | closed      | deferred    |
            | deferred    | in_progress |
            | deferred    | blocked     |

    Scenario: Type-specific workflow overrides default
        Given a Kanbus project with default configuration
        And an issue "kanbus-epic01" of type "epic" with status "open"
        When I run "kanbus update kanbus-epic01 --status deferred"
        Then the command should fail with exit code 1
        And stderr should contain "invalid transition"
```

`features/workflow/automatic_side_effects.feature`:

```gherkin
Feature: Automatic side effects on status transitions
    Scenario: Closing an issue sets closed_at timestamp
        Given a Kanbus project with default configuration
        And an issue "kanbus-test01" of type "task" with status "open"
        And issue "kanbus-test01" has no closed_at timestamp
        When I run "kanbus update kanbus-test01 --status closed"
        Then issue "kanbus-test01" should have a closed_at timestamp

    Scenario: Reopening an issue clears closed_at timestamp
        Given a Kanbus project with default configuration
        And an issue "kanbus-test01" of type "task" with status "closed"
        And issue "kanbus-test01" has a closed_at timestamp
        When I run "kanbus update kanbus-test01 --status open"
        Then issue "kanbus-test01" should have no closed_at timestamp
```

`features/workflow/claim_workflow.feature`:

```gherkin
Feature: Claim workflow
    Scenario: Claiming an issue sets assignee and transitions to in_progress
        Given a Kanbus project with default configuration
        And an issue "kanbus-test01" of type "task" with status "open"
        And the current user is "dev@example.com"
        When I run "kanbus update kanbus-test01 --claim"
        Then issue "kanbus-test01" should have status "in_progress"
        And issue "kanbus-test01" should have assignee "dev@example.com"
```

#### Task 3.2: Implement workflows in Python

`workflows.py`:
- `validate_status_transition(configuration, issue_type, current_status, new_status) -> None` (raises `InvalidTransitionError`)
- `get_workflow_for_issue_type(configuration, issue_type) -> WorkflowDefinition`
- `apply_transition_side_effects(issue, new_status, current_utc_time) -> IssueData`

#### Task 3.3: Implement workflows in Rust

`workflows.rs`:
- `validate_status_transition(config, issue_type, current, new) -> Result<()>`
- `get_workflow_for_issue_type(config, issue_type) -> &WorkflowDefinition`
- `apply_transition_side_effects(issue, new_status, now) -> IssueData`

---

### Epic 4: Hierarchy Enforcement

**Goal:** Parent-child relationships between issues are strictly validated against the configured hierarchy.

**Dependencies:** Epic 2 (needs models).

#### Task 4.1: Write Gherkin scenarios for hierarchy validation

`features/hierarchy/parent_child_validation.feature`:

```gherkin
Feature: Parent-child hierarchy validation
    Scenario Outline: Valid parent-child relationships
        Given a Kanbus project with default configuration
        And a "<parent_type>" issue "kanbus-parent" exists
        When I run "kanbus create Child Task --type <child_type> --parent kanbus-parent"
        Then the command should succeed

        Examples:
            | parent_type | child_type |
            | initiative  | epic       |
            | epic        | task       |
            | task        | sub-task   |
            | epic        | bug        |
            | task        | story      |

    Scenario Outline: Invalid parent-child relationships
        Given a Kanbus project with default configuration
        And a "<parent_type>" issue "kanbus-parent" exists
        When I run "kanbus create Child Task --type <child_type> --parent kanbus-parent"
        Then the command should fail with exit code 1
        And stderr should contain "invalid parent-child"

        Examples:
            | parent_type | child_type  |
            | epic        | initiative  |
            | task        | epic        |
            | sub-task    | task        |
            | bug         | task        |
            | story       | sub-task    |

    Scenario: Standalone issues do not require a parent
        Given a Kanbus project with default configuration
        When I run "kanbus create Standalone Task --type task"
        Then the command should succeed
        And the created issue should have no parent

    Scenario: Non-hierarchical types cannot have children
        Given a Kanbus project with default configuration
        And a "bug" issue "kanbus-bug01" exists
        When I run "kanbus create Child --type task --parent kanbus-bug01"
        Then the command should fail with exit code 1
```

#### Task 4.2: Implement hierarchy in Python

`hierarchy.py`:
- `validate_parent_child_relationship(configuration, parent_type, child_type) -> None` (raises `InvalidHierarchyError`)
- `get_allowed_child_types(configuration, parent_type) -> list[str]`

#### Task 4.3: Implement hierarchy in Rust

`hierarchy.rs`:
- `validate_parent_child_relationship(config, parent_type, child_type) -> Result<()>`
- `get_allowed_child_types(config, parent_type) -> Vec<String>`

---

### Epic 5: Issue CRUD Operations

**Goal:** Users can create, read, update, and delete issues through the CLI.

**Dependencies:** Epics 1-4 (needs init, models, workflows, hierarchy).

#### Task 5.1: Write Gherkin scenarios for issue creation

`features/issues/issue_creation.feature`:

```gherkin
Feature: Issue creation
    Scenario: Create a basic task with defaults
        Given a Kanbus project with default configuration
        When I run "kanbus create Implement OAuth2 flow"
        Then the command should succeed
        And stdout should contain a valid issue ID
        And an issue file should be created in the issues directory
        And the created issue should have title "Implement OAuth2 flow"
        And the created issue should have type "task"
        And the created issue should have status "open"
        And the created issue should have priority 2
        And the created issue should have an empty labels list
        And the created issue should have an empty dependencies list
        And the created issue should have a created_at timestamp
        And the created issue should have an updated_at timestamp

    Scenario: Create an issue with all options specified
        Given a Kanbus project with default configuration
        And an "epic" issue "kanbus-epic01" exists
        When I run "kanbus create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent kanbus-epic01 --label auth --label urgent --description Bug in login"
        Then the command should succeed
        And the created issue should have type "bug"
        And the created issue should have priority 1
        And the created issue should have assignee "dev@example.com"
        And the created issue should have parent "kanbus-epic01"
        And the created issue should have labels "auth, urgent"
        And the created issue should have description "Bug in login"

    Scenario: Create an issue with invalid type
        Given a Kanbus project with default configuration
        When I run "kanbus create Bad Issue --type nonexistent"
        Then the command should fail with exit code 1
        And stderr should contain "unknown issue type"

    Scenario: Create an issue with nonexistent parent
        Given a Kanbus project with default configuration
        When I run "kanbus create Orphan --parent kanbus-nonexistent"
        Then the command should fail with exit code 1
        And stderr should contain "not found"
```

#### Task 5.2: Write Gherkin scenarios for issue display, update, close, delete

Similar detailed scenarios for `kanbus show`, `kanbus update`, `kanbus close`, `kanbus delete`. Each scenario specifies expected behavior precisely.

#### Task 5.3: Implement CRUD in Python

- `cli.py`: Click commands for `create`, `show`, `update`, `close`, `delete`
- Integration with `models.py`, `file_io.py`, `workflows.py`, `hierarchy.py`, `ids.py`

#### Task 5.4: Implement CRUD in Rust

- `cli.rs`: Clap commands for `create`, `show`, `update`, `close`, `delete`
- Integration with all domain modules

---

### Epic 6: In-Memory Index and Cache

**Goal:** The system can efficiently scan issue files, build lookup maps, and cache the result for fast subsequent invocations.

**Dependencies:** Epic 5 (needs issues to exist to index them).

#### Task 6.1: Write Gherkin scenarios for index behavior

`features/index/index_building.feature`:

```gherkin
Feature: In-memory index building
    Scenario: Index builds lookup maps from issue files
        Given a Kanbus project with 5 issues of varying types and statuses
        When the index is built
        Then the index should contain 5 issues
        And querying by status "open" should return the correct issues
        And querying by type "task" should return the correct issues
        And querying by parent should return the correct children

    Scenario: Index computes reverse dependency links
        Given a Kanbus project with default configuration
        And issue "kanbus-aaa" exists with a blocked-by dependency on "kanbus-bbb"
        When the index is built
        Then the reverse dependency index should show "kanbus-bbb" blocks "kanbus-aaa"
```

`features/index/cache_invalidation.feature`:

```gherkin
Feature: Cache invalidation
    Scenario: Cache is created on first run
        Given a Kanbus project with issues but no cache file
        When any kanbus command is run
        Then a cache file should be created in project/.cache/index.json

    Scenario: Cache is used when issue files have not changed
        Given a Kanbus project with a valid cache
        When any kanbus command is run
        Then the cache should be loaded without re-scanning issue files

    Scenario: Cache is rebuilt when an issue file changes
        Given a Kanbus project with a valid cache
        When an issue file is modified (mtime changes)
        And any kanbus command is run
        Then the cache should be rebuilt from the issue files

    Scenario: Cache is rebuilt when an issue file is added
        Given a Kanbus project with a valid cache
        When a new issue file appears in the issues directory
        And any kanbus command is run
        Then the cache should be rebuilt

    Scenario: Cache is rebuilt when an issue file is deleted
        Given a Kanbus project with a valid cache
        When an issue file is removed from the issues directory
        And any kanbus command is run
        Then the cache should be rebuilt
```

#### Daemon Availability Contract

The local indexing daemon is an optimization layer for cache warm-up and IPC access to the index.
The JSON issue files remain the source of truth at all times.

Explicit behavior:
- If a local daemon is running, CLI commands request the index over IPC.
- If the daemon is unavailable, CLI commands scan the issue files directly.
- This is a defined product behavior, not a fallback to an alternate storage system.

#### Task 6.2: Implement index in Python

`index.py`:
- `IssueIndex` class with fields: `by_id`, `by_status`, `by_type`, `by_parent`, `by_label`, `reverse_dependencies`
- `build_index_from_directory(issues_directory) -> IssueIndex`

`cache.py`:
- `IndexCache` class
- `load_cache_if_valid(cache_path, issues_directory) -> Optional[IssueIndex]`
- `write_cache(index, cache_path, file_modification_times)`
- Cache invalidation: compare file list and mtimes

#### Task 6.3: Implement index in Rust

`index.rs` and `cache.rs` -- same structure, `HashMap`-based lookups, `serde` for cache serialization.

---

### Epic 7: Dependencies and Cycle Detection

**Goal:** Users can add and remove dependencies between issues. `blocked-by` dependencies form a DAG; cycles are detected and rejected.

**Dependencies:** Epic 5 (needs CRUD), Epic 6 (needs index for reverse lookups).

#### Task 7.1: Write Gherkin scenarios for dependencies

`features/dependencies/blocked_by_dependencies.feature`:

```gherkin
Feature: Blocked-by dependencies
    Scenario: Add a blocked-by dependency
        Given a Kanbus project with default configuration
        And issues "kanbus-aaa" and "kanbus-bbb" exist
        When I run "kanbus dep add kanbus-aaa --blocked-by kanbus-bbb"
        Then the command should succeed
        And issue "kanbus-aaa" should have a blocked-by dependency on "kanbus-bbb"

    Scenario: Remove a dependency
        Given a Kanbus project with default configuration
        And issue "kanbus-aaa" has a blocked-by dependency on "kanbus-bbb"
        When I run "kanbus dep remove kanbus-aaa kanbus-bbb"
        Then the command should succeed
        And issue "kanbus-aaa" should have no dependencies
```

`features/dependencies/cycle_detection.feature`:

```gherkin
Feature: Dependency cycle detection
    Scenario: Reject a direct cycle
        Given a Kanbus project with default configuration
        And issue "kanbus-aaa" has a blocked-by dependency on "kanbus-bbb"
        When I run "kanbus dep add kanbus-bbb --blocked-by kanbus-aaa"
        Then the command should fail with exit code 1
        And stderr should contain "cycle"

    Scenario: Reject a transitive cycle
        Given a Kanbus project with default configuration
        And issue "kanbus-aaa" is blocked-by "kanbus-bbb"
        And issue "kanbus-bbb" is blocked-by "kanbus-ccc"
        When I run "kanbus dep add kanbus-ccc --blocked-by kanbus-aaa"
        Then the command should fail with exit code 1
        And stderr should contain "cycle"

    Scenario: relates-to dependencies do not participate in cycle detection
        Given a Kanbus project with default configuration
        And issue "kanbus-aaa" has a relates-to dependency on "kanbus-bbb"
        When I run "kanbus dep add kanbus-bbb --relates-to kanbus-aaa"
        Then the command should succeed
```

`features/dependencies/ready_query.feature`:

```gherkin
Feature: Ready query
    Scenario: An open issue with no blockers is ready
        Given a Kanbus project with an open issue "kanbus-aaa" and no dependencies
        When I run "kanbus ready"
        Then "kanbus-aaa" should appear in the results

    Scenario: An open issue blocked by an open issue is not ready
        Given a Kanbus project with default configuration
        And an open issue "kanbus-aaa" blocked-by open issue "kanbus-bbb"
        When I run "kanbus ready"
        Then "kanbus-aaa" should not appear in the results
        And "kanbus-bbb" should appear in the results

    Scenario: An open issue blocked by a closed issue is ready
        Given a Kanbus project with default configuration
        And an open issue "kanbus-aaa" blocked-by closed issue "kanbus-bbb"
        When I run "kanbus ready"
        Then "kanbus-aaa" should appear in the results

    Scenario: A closed issue is never ready
        Given a Kanbus project with a closed issue "kanbus-aaa"
        When I run "kanbus ready"
        Then "kanbus-aaa" should not appear in the results

    Scenario: An in_progress issue is not ready
        Given a Kanbus project with an in_progress issue "kanbus-aaa"
        When I run "kanbus ready"
        Then "kanbus-aaa" should not appear in the results
```

#### Task 7.2: Implement dependencies in Python

`dependencies.py`:
- `add_blocked_by_dependency(index, source_issue_id, target_issue_id) -> IssueData`
- `add_relates_to_dependency(index, source_issue_id, target_issue_id) -> IssueData`
- `remove_dependency(issue, target_issue_id) -> IssueData`
- `detect_blocked_by_cycle(index, source_id, proposed_target_id) -> bool` (DFS on the blocked-by graph)
- `find_ready_issues(index) -> list[IssueData]`

#### Task 7.3: Implement dependencies in Rust

Same functions, same algorithm (DFS for cycle detection), Rust idioms.

---

### Epic 8: Query Commands

**Goal:** `kanbus list`, `kanbus ready`, `kanbus blocked`, `kanbus search` provide filtered views of the issue database.

**Dependencies:** Epic 6 (needs index).

#### Task 8.1: Write Gherkin scenarios for queries

Detailed scenarios for each filter combination, sorting, limits, JSON output, and the special `ready` and `blocked` views.

#### Task 8.2-8.3: Implement in Python and Rust

`queries.py` / `queries.rs`:
- `execute_list_query(index, filters) -> list[IssueData]`
- `execute_full_text_search(index, search_text) -> list[IssueData]`
- Output formatting: human-readable table and `--json` mode

---

### Epic 9: Comments

**Goal:** Users can add comments to issues.

**Dependencies:** Epic 5 (needs CRUD).

#### Task 9.1: Gherkin scenarios

```gherkin
Feature: Issue comments
    Scenario: Add a comment to an issue
        Given a Kanbus project with default configuration
        And an issue "kanbus-aaa" exists
        When I run 'kanbus comment kanbus-aaa "This is a comment"'
        Then the command should succeed
        And issue "kanbus-aaa" should have 1 comment
        And the comment should have text "This is a comment"
        And the comment should have a created_at timestamp

    Scenario: Comments appear in issue display
        Given an issue "kanbus-aaa" with 2 comments
        When I run "kanbus show kanbus-aaa"
        Then stdout should display both comments in chronological order
```

#### Task 9.2-9.3: Implement in Python and Rust

Straightforward: append to `comments` list, update `updated_at`, write file.

---

### Epic 10: Wiki System

**Goal:** Wiki pages with Jinja2 templates render with live issue data.

**Dependencies:** Epic 6 (needs index for queries).

#### Task 10.1: Write Gherkin scenarios for wiki rendering

`features/wiki/wiki_rendering.feature`:

```gherkin
Feature: Wiki rendering
    Scenario: Render a wiki page with a simple query
        Given a Kanbus project with default configuration
        And 3 open tasks and 2 closed tasks exist
        And a wiki page "status.md" with content:
            """
            Open: {{ count(status="open") }}
            Closed: {{ count(status="closed") }}
            """
        When I run "kanbus wiki render project/wiki/status.md"
        Then stdout should contain "Open: 3"
        And stdout should contain "Closed: 2"

    Scenario: Render a wiki page with a for loop
        Given a Kanbus project with default configuration
        And open tasks "Alpha" and "Beta" exist
        And a wiki page "tasks.md" with content:
            """
            {% for issue in query(status="open", sort="title") %}
            - {{ issue.title }}
            {% endfor %}
            """
        When I run "kanbus wiki render project/wiki/tasks.md"
        Then stdout should contain "- Alpha"
        And stdout should contain "- Beta"
        And "Alpha" should appear before "Beta" in the output
```

`features/wiki/wiki_template_functions.feature`:

Scenarios for each template function: `query`, `count`, `issue`, `children`, `blocked_by`, `blocks`.

#### Task 10.2: Implement wiki in Python

`wiki.py`:
- `WikiRenderer` class
- `render_wiki_page(page_path, index) -> str`
- Template context registration: `query`, `count`, `issue`, `children`, `blocked_by`, `blocks`
- Uses Jinja2 `Environment` with `FileSystemLoader`

#### Task 10.3: Implement wiki in Rust

`wiki.rs`:
- Uses MiniJinja `Environment`
- Same template functions registered as MiniJinja functions
- Careful attention to filter/function signature compatibility with Jinja2

---

### Epic 11: Maintenance Commands

**Goal:** `kanbus validate` checks integrity, `kanbus stats` shows project overview.

**Dependencies:** Epic 6 (needs index).

#### Task 11.1: Write Gherkin scenarios

```gherkin
Feature: Project validation
    Scenario: Valid project passes validation
        Given a Kanbus project with consistent data
        When I run "kanbus validate"
        Then the command should succeed
        And stdout should contain "no issues found"

    Scenario: Dangling parent reference detected
        Given a Kanbus project where issue "kanbus-aaa" references parent "kanbus-nonexistent"
        When I run "kanbus validate"
        Then the command should fail with exit code 1
        And stderr should contain "dangling parent reference"

    Scenario: Dangling dependency target detected
        ...

    Scenario: Hierarchy violation detected
        ...

    Scenario: Blocked-by cycle detected
        ...
```

#### Task 11.2-11.3: Implement in Python and Rust

`kanbus validate` runs all integrity checks and reports all errors (not just the first one). `kanbus stats` aggregates counts by type, status, priority, and reports blockers.

---

### Epic 12: Dependency Tree Display

**Goal:** `kanbus dep tree <id>` renders a visual dependency tree.

**Dependencies:** Epic 7.

Brief epic -- write scenarios for tree display format, implement ASCII tree rendering in both languages.

---

### Epic 13: Polish and Edge Cases

**Goal:** Handle all edge cases, improve error messages, ensure JSON output mode works everywhere.

- `--json` flag on all commands
- Graceful handling of corrupted JSON files
- Graceful handling of missing config
- Signal handling / partial write protection
- Descriptive error messages for every failure mode

---

### Epic 15: GitHub Issue Sync

**Goal:** Bidirectional sync between the Kanbus plan repository and GitHub Issues. Every Kanbus issue file has a corresponding GitHub issue whose body contains a clickable link to that file (blob URL). Every GitHub issue that does not link back to a Kanbus issue gets a new Kanbus issue created and its body updated with the link.

**Dependencies:** Epic 5 (CRUD), Epic 6 (index).

Sync runs via GitHub Actions using the `gh` CLI only. The link from each GitHub issue to the source JSON file is a blob URL built from `GITHUB_REPOSITORY`, default branch, and relative path (e.g. `project/issues/kanbus-a1b2c3.json`). See `docs/GITHUB_SYNC.md` for link format and discovery.

#### Task 15.1: Link format and discovery

- Define body format: blob URL plus HTML comment `<!-- kanbus-source: project/issues/kanbus-abc.json -->` for parsing.
- Document derivation of blob URL from `GITHUB_REPOSITORY`, default branch (`gh repo view --json defaultBranchRef`), and relative path.
- No Gherkin; document in epic and in `docs/GITHUB_SYNC.md`.

#### Task 15.2: Kanbus to GitHub (ensure link exists)

- For each `project/issues/{id}.json`, ensure a GitHub issue exists with the blob link in the body.
- If no GitHub issue: create one (title from issue, body with description and source link). Optionally store `custom.github_issue_number` in JSON.
- If GitHub issue exists but body lacks link: edit body to add link (preserve existing content).
- Script uses `gh issue list`, `gh issue create`, `gh issue view`, `gh issue edit`.

#### Task 15.3: GitHub to Kanbus (create missing issues)

- List GitHub issues; for each, parse body for Kanbus source marker.
- If no source link: create new Kanbus issue (new ID, write `project/issues/{id}.json`), then update GitHub issue body with blob link and marker.
- Copy title and optional description from GitHub issue into new JSON.

#### Task 15.4: GitHub Action workflow

- New workflow `.github/workflows/sync-github-issues.yml`: runs on schedule (e.g. daily) and/or on push to `main`; checks out repo; runs sync script via `gh`.
- Permissions: `issues: write`, `contents: read`; use `GITHUB_TOKEN`.

#### Task 15.5: Sync script and documentation

- Sync is script-only (`tools/sync_github_issues.py`), invoked by the workflow. No `kanbus sync-github` CLI in this epic; document in `docs/GITHUB_SYNC.md` how to run sync locally (e.g. `python tools/sync_github_issues.py --dry-run`).

---

## Part 3: Quality Enforcement Strategy

### The Quality Gate Pipeline

Every change must pass this pipeline before merging. No exceptions. The pipeline runs locally via `make check-all` and in CI via GitHub Actions.

```
STAGE 1: Format Verification (fast, catches style drift immediately)
    Python: black --check python/
    Python: ruff check python/
    Rust:   cargo fmt --check (in rust/)
    Rust:   cargo clippy -- -D warnings (in rust/)

STAGE 2: Documentation Verification
    Python: Custom script verifies every public class/method has a Sphinx docstring
    Rust:   cargo doc --no-deps (warnings are errors; missing docs = build failure)
            (Use #![warn(missing_docs)] in lib.rs)

STAGE 3: Spec Parity Verification
    Run:    python tools/check_spec_parity.py
    Logic:  - Parse all .feature files in features/
            - Extract every Scenario and Scenario Outline
            - Parse Python step definitions to find which steps are implemented
            - Parse Rust step definitions to find which steps are implemented
            - Report any scenario that is NOT covered by both implementations
            - Exit code 1 if any gap exists

STAGE 4: Behavior Specs (the core quality gate)
    Python: cd python && behave
            (behavior specs: cd python && behave)
    Rust:   cd rust && cargo test --test cucumber -- --tags "not @wip"

STAGE 5: YAML Test Cases
    Python: cd python && behave
    Rust:   cd rust && cargo test --test spec_runner

STAGE 6: Coverage Reporting
    Python: coverage run --source=kanbus -m behave -c behave.ini
    Rust:   cargo tarpaulin --out Stdout --fail-under 100
            (or cargo llvm-cov with threshold)
```

### Naming Conventions (Enforced by Linters and Review)

**Python:**
- Classes: `PascalCase` (e.g., `IssueData`, `ProjectConfiguration`, `WikiRenderer`)
- Functions/methods: `snake_case`, long and descriptive (e.g., `validate_status_transition`, `build_index_from_directory`)
- No abbreviations: `configuration` not `config` in variable names, `dependency` not `dep`
- Constants: `SCREAMING_SNAKE_CASE`

**Rust:**
- Structs/enums: `PascalCase` (e.g., `IssueData`, `ProjectConfiguration`)
- Functions/methods: `snake_case`, same descriptive style
- Module names: `snake_case`
- Constants: `SCREAMING_SNAKE_CASE`

**Gherkin:**
- Feature names: sentence case, describe the capability
- Scenario names: sentence case, describe the specific behavior
- Step text: natural English, present tense
- No abbreviations in step text

### Docstring Standards

**Python (Sphinx-style):**
```python
def validate_status_transition(
    configuration: ProjectConfiguration,
    issue_type: str,
    current_status: str,
    new_status: str,
) -> None:
    """Validate that a status transition is permitted by the workflow.

    Looks up the workflow for the given issue type in the project
    configuration (falling back to the default workflow if no
    type-specific workflow exists), then verifies that the new status
    appears in the list of allowed transitions from the current status.

    :param configuration: The loaded project configuration containing
        workflow definitions.
    :param issue_type: The type of the issue being transitioned (e.g.,
        "task", "epic").
    :param current_status: The issue's current status.
    :param new_status: The desired new status.
    :raises InvalidTransitionError: If the transition is not permitted
        by the workflow.
    """
```

**Rust (doc comments):**
```rust
/// Validate that a status transition is permitted by the workflow.
///
/// Looks up the workflow for the given issue type in the project
/// configuration (falling back to the default workflow if no
/// type-specific workflow exists), then verifies that the new status
/// appears in the list of allowed transitions from the current status.
///
/// # Arguments
///
/// * `configuration` - The loaded project configuration containing
///   workflow definitions.
/// * `issue_type` - The type of the issue being transitioned.
/// * `current_status` - The issue's current status.
/// * `new_status` - The desired new status.
///
/// # Errors
///
/// Returns `InvalidTransitionError` if the transition is not permitted
/// by the workflow.
pub fn validate_status_transition(
    configuration: &ProjectConfiguration,
    issue_type: &str,
    current_status: &str,
    new_status: &str,
) -> Result<(), WorkflowError> {
```

### Comment Policy

- NO line-level comments (e.g., `x = x + 1  # increment x`)
- Block-level comments ONLY for higher-level architectural context:

```python
#
# The cache invalidation strategy is intentionally coarse-grained.
# If ANY file's mtime has changed, or the file list differs, we
# rebuild the entire index. This avoids partial-update bugs at the
# cost of a full rebuild that takes ~10-50ms on 1000 issues.
#
def load_cache_if_valid(
    cache_path: Path,
    issues_directory: Path,
) -> Optional[IssueIndex]:
```

### Continuous Quality Enforcement

**Pre-commit hook:** Runs `ruff check`, `black --check`, `cargo fmt --check`, `cargo clippy` on staged files. Fast enough to run on every commit.

**CI pipeline (GitHub Actions):** Runs the full 6-stage pipeline on every push and PR. PRs cannot merge with any stage failing.

**Makefile targets:**
```makefile
check-python:     ## Run all Python quality gates
check-rust:       ## Run all Rust quality gates
check-parity:     ## Verify spec parity between implementations
check-all:        ## Run everything
fmt:              ## Auto-format both codebases
specs:            ## Run only the behavior specs (both languages)
```

---

## Part 4: Spec Parity Approach

### The Central Idea

There is ONE set of Gherkin feature files in `features/`. Both implementations read these same files and execute them. This is not a metaphor -- the same `.feature` file on disk is loaded by `behave` in Python and by `cucumber-rs` in Rust.

### How Behave Finds the Features

In `python/behave.ini`:

```ini
[behave]
paths = ../features
tags = ~wip
```

Behave expects step definitions in `python/features/steps` and discovers `../features` via the path to the shared `features` directory. `python/features/environment.py` adds `python/` and `python/src` to `sys.path` for imports.

### How cucumber-rs Finds the Features

In `rust/tests/cucumber.rs`:

```rust
use cucumber::World;

#[tokio::main]
async fn main() {
    KanbusWorld::run("tests/features/").await;
    // tests/features/ is a path to ../../features/
}
```

The path `rust/tests/features/` points to `../../features/`, so cucumber-rs discovers the same feature files.

### Step Definition Parity

Step definitions in Python and Rust must implement the SAME Given/When/Then steps. The naming is intentionally parallel:

| Feature Domain | Python Step File | Rust Step File |
|---|---|---|
| Common setup | `common_steps.py` | `common_steps.rs` |
| Initialization | `initialization_steps.py` | `initialization_steps.rs` |
| Issue CRUD | `issue_crud_steps.py` | `issue_crud_steps.rs` |
| Workflows | `workflow_steps.py` | `workflow_steps.rs` |
| Hierarchy | `hierarchy_steps.py` | `hierarchy_steps.rs` |
| Dependencies | `dependency_steps.py` | `dependency_steps.rs` |
| Queries | `query_steps.py` | `query_steps.rs` |
| Comments | `comment_steps.py` | `comment_steps.rs` |
| Wiki | `wiki_steps.py` | `wiki_steps.rs` |
| Maintenance | `maintenance_steps.py` | `maintenance_steps.rs` |
| Index | `index_steps.py` | `index_steps.rs` |

### The Parity Checker

`tools/check_spec_parity.py` is a critical CI tool that:

1. Parses every `.feature` file and extracts all step texts (Given/When/Then patterns)
2. Parses Python step definitions and extracts all registered step patterns
3. Parses Rust step definitions and extracts all registered step patterns (via regex on `#[given]`, `#[when]`, `#[then]` attributes)
4. Computes the intersection and differences
5. Reports:
   - Steps defined in features but missing from Python
   - Steps defined in features but missing from Rust
   - Steps defined in Python but not Rust (implementation drift)
   - Steps defined in Rust but not Python (implementation drift)
6. Exits with code 1 if ANY asymmetry exists

This ensures that neither implementation silently falls behind. The CI pipeline will not pass if spec parity is broken.

### YAML Test Case Runners

Both implementations also provide a runner for the YAML test case format described in VISION.md. This runner:

1. Discovers all `test.yaml` files under `specs/test-cases/`
2. For each test case:
   - Creates a temporary directory
   - Copies the `input/` directory contents into a proper project structure
   - Invokes the `kanbus` binary (or the library API directly) with the specified command
   - Asserts exit code, stdout/stderr content, and resulting file states
3. Reports pass/fail per test case

The YAML test cases and Gherkin scenarios are complementary:
- **Gherkin** is better for describing behavior in human-readable terms and for driving the design conversation
- **YAML test cases** are better for exhaustive data-driven coverage of edge cases (e.g., every valid/invalid transition in every workflow)

### Handling Feature Development Incrementally

When starting a new epic:

1. Write the `.feature` file in `features/` with all scenarios
2. Tag unimplemented scenarios with `@wip`
3. Implement step definitions in Python, removing `@wip` as scenarios pass
4. Implement step definitions in Rust, removing `@wip` as scenarios pass
5. The parity checker validates that both implementations cover the same set of non-`@wip` scenarios
6. An epic is not complete until all scenarios in its feature files have the `@wip` tag removed and pass in both implementations

This means at any point in time, the codebase is in one of these states:
- **Green:** All non-`@wip` scenarios pass in both implementations. Parity is maintained.
- **Yellow:** A feature is in progress. Some scenarios are `@wip`. All non-`@wip` scenarios still pass in both.
- **Red:** Something is broken. CI fails. Must be fixed before merging.

The `@wip` tag acts as an explicit acknowledgment of incomplete work, visible in the feature files themselves.

---

## Part 5: Implementation Order (Summary)

```
Epic 0:  Repository Bootstrap                    (no Gherkin)
Epic 1:  Project Initialization (kanbus init)       (4-6 scenarios)
Epic 2:  Data Model and Configuration            (8-12 scenarios)
Epic 3:  Workflow State Machine                   (20-30 scenarios, heavy use of Scenario Outline)
Epic 4:  Hierarchy Enforcement                    (12-16 scenarios)
Epic 5:  Issue CRUD Operations                    (20-30 scenarios)
Epic 6:  In-Memory Index and Cache                (8-12 scenarios)
Epic 7:  Dependencies and Cycle Detection         (15-20 scenarios)
Epic 8:  Query Commands                           (15-20 scenarios)
Epic 9:  Comments                                 (4-6 scenarios)
Epic 10: Wiki System                              (15-20 scenarios)
Epic 11: Maintenance Commands                     (8-12 scenarios)
Epic 12: Dependency Tree Display                  (4-6 scenarios)
Epic 13: Polish and Edge Cases                    (10-15 scenarios)
Epic 15: GitHub Issue Sync                       (script-only; see docs/GITHUB_SYNC.md)
```

**Total estimated scenarios: 145-200.**

Each epic depends on the ones before it. Within an epic, the flow is always:

1. Write Gherkin (specs/)
2. Implement Python (python/)
3. Implement Rust (rust/)
4. Run parity checker
5. All quality gates green
6. Epic complete

---

## Part 6: Operational Notes

### Local Development Workflow

A developer working on Kanbus should be able to:

```bash
make fmt          # Auto-format everything
make check-all    # Run all quality gates (takes ~30 seconds)
make specs        # Run just the behavior specs (~10 seconds)
make check-parity # Run just the parity checker (~2 seconds)
```

### The First 30 Minutes

When a new contributor clones the repo:

```bash
git clone https://github.com/.../Kanbus.git
cd Kanbus
make setup        # Installs Python venv + deps, checks Rust toolchain
make check-all    # Everything green
```

### Error Message Philosophy

Every error message from `kanbus` should:
- State what went wrong in plain English
- State what was expected vs. what was found
- Suggest what the user can do to fix it

Example:
```
Error: Invalid status transition from 'open' to 'blocked' for type 'task'.

The 'default' workflow allows these transitions from 'open':
  - in_progress
  - closed
  - deferred

To see the full workflow: kanbus show-workflow task
```

This is tested in the Gherkin scenarios by asserting on stderr content.

---

## Appendix: Technology Choices for BDD Tooling

### Python: Behave

**Why:** Behave is a mature Gherkin runner for Python. Step definitions are Python functions decorated with `@given`, `@when`, `@then`. Supports Scenario Outlines with Examples tables. Feature files are standard Gherkin.

**Configuration in `behave.ini`:**
```ini
[behave]
paths = ../features
tags = ~wip
```

### Rust: cucumber-rs

**Why:** The most mature Gherkin runner for Rust. Supports async, has a World pattern for test state, and reads standard `.feature` files. Step definitions use `#[given]`, `#[when]`, `#[then]` attribute macros.

**Configuration in `Cargo.toml`:**
```toml
[[test]]
name = "cucumber"
harness = false

[dev-dependencies]
cucumber = "0.21"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

### Parity Checker: Custom Python Script

A ~200-line Python script that uses the `gherkin-official` parser (or regex-based extraction) to compare feature steps against step definition registrations. This is not a testing framework -- it is a structural analysis tool that answers: "Are both implementations covering the same specification?"

---

This plan is designed to produce a codebase where:
- The specifications are the product
- The code is a joy to read
- Quality is enforced automatically, not manually
- A developer can work on any domain and see the spec, the Python, and the Rust side by side
- Neither implementation can silently drift from the other
