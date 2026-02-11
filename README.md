# Taskulus

**A git-backed project management system with dual Python and Rust implementations**

![Python CI](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/AnthusAI/Taskulus/badges/python-ci.json)
![Rust CI](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/AnthusAI/Taskulus/badges/rust-ci.json)
![Python Coverage](https://codecov.io/gh/AnthusAI/Taskulus/branch/main/graph/badge.svg?flag=python)
![Rust Coverage](https://codecov.io/gh/AnthusAI/Taskulus/branch/main/graph/badge.svg?flag=rust)

Taskulus is a lightweight, file-based issue tracker that stores all data as JSON files in your git repository. It replaces external tools like Jira and Confluence with a simple, version-controlled system that lives alongside your code.

## Status: Planning Phase

This repository contains the complete vision, implementation plan, and task breakdown for building Taskulus. We have **118 beads (tasks)** organized into **18 epics** with clear dependencies and acceptance criteria.

## Quick Overview

- **Issue Storage**: Each issue is a separate JSON file in `project/issues/`
- **Wiki System**: Jinja2-powered markdown templates with live issue queries
- **Dual Implementation**: Python for easy installation, Rust for maximum performance
- **Shared Specs**: Both implementations pass identical BDD scenarios
- **Git-Native**: All data is plain files, version-controlled with git

## Key Features

- Issue tracking with strict hierarchy (initiative -> epic -> task -> sub-task)
- Workflow state machines with configurable transitions
- Dependency management with cycle detection
- Full-text search across titles, descriptions, and comments
- Wiki pages with live issue data using Jinja2 templates
- Migration path from Beads (JSONL format)

## Python vs Rust: Which Should I Use?

**Choose Python if:**
- You want easy `pip install` with no compilation
- Your project has < 500 issues
- You prefer Python tooling and ecosystem

**Choose Rust if:**
- You need maximum performance (sub-millisecond cache loads)
- Your project has > 2000 issues
- You're comfortable with `cargo install` or pre-built binaries

**Both implementations are functionally identical** - they pass the same behavior tests and produce the same output.

## Installation

Taskulus is in the planning phase. The commands below describe the intended install paths for the first release. For current development setup, see GETTING_STARTED.md.

Python (pip):

```bash
pip install taskulus
```

Rust (cargo):

```bash
cargo install taskulus
```

## Quick Start (5 Commands)

```bash
tsk init
tsk create "Set up the project structure"
tsk list
tsk show tsk-<id>
tsk close tsk-<id>
```

## Project Structure

```
Taskulus/
|-- planning/
|   |-- VISION.md                  # Complete specification (27KB)
|   `-- IMPLEMENTATION_PLAN.md     # Detailed implementation plan
|-- specs/                          # Shared Gherkin feature files
|-- python/                         # Python implementation
|-- rust/                           # Rust implementation
|-- tools/                          # Quality checking scripts
|-- AGENTS.md                       # Code quality standards
`-- .beads/                        # Beads task database
```

## Implementation Plan Overview

### Phase 1: Foundation (Epics 0-6)
Build the core functionality: initialization, data models, CRUD operations, workflows, hierarchy, and basic indexing.

**Milestone 1 (M1)**: After Epic 6, you can create, show, update, close, and delete issues.

### Phase 2: Query and Collaboration (Epics 7-10)
Add advanced indexing, dependency management, queries, search, and comments.

**Milestone 2 (M2)**: After Epic 9, you can query and filter issues effectively for planning.

### Phase 3: Wiki System (Epic 11)
Implement Jinja2/MiniJinja wiki rendering with live issue data.

**Milestone 3 (M3)**: After Epic 11, you can use Taskulus to track Taskulus (self-hosting).

### Phase 4: Polish and Release (Epics 12-17)
Add maintenance commands, dependency tree display, migration from Beads, comprehensive documentation, installation testing, and final polish.

**Milestone 4 (M4)**: 1.0 Release - all features complete, production-ready.

## Current Status

### Beads Task Database

We're using Beads (the predecessor to Taskulus) to manage the Taskulus project itself:

- **118 total tasks** across 18 epics
- **99 ready to work** (no blocking dependencies)
- **19 blocked** (waiting on prerequisites)
- Clear dependency chains between epics

### All Epics

| ID | Epic | Dependencies | Tasks |
|----|------|--------------|-------|
| tskl-zqm | Repository Bootstrap and Foundation | - | 4 |
| tskl-mel | Project Initialization (tsk init) | Epic 0 | 4 |
| tskl-1z1 | Data Models and Configuration | Epic 1 | 7 |
| tskl-1i0 | Workflow State Machine | Epic 2 | 4 |
| tskl-cih | Hierarchy Enforcement | Epic 2 | 4 |
| tskl-20z | Basic Index and File Scanning | Epic 2 | 4 |
| tskl-9w4 | Issue CRUD Operations | Epics 3, 4, 5 | 14 |
| tskl-fzn | Advanced Index and Cache System | Epic 6 | 5 |
| tskl-538 | Dependency Management | Epics 6, 7 | 4 |
| tskl-5er | Query and List Operations | Epic 7 | 4 |
| tskl-76b | Comments System | Epic 6 | 4 |
| tskl-eyu | Wiki System | Epic 7 | 6 |
| tskl-8ke | Maintenance Commands | Epic 7 | 5 |
| tskl-p3i | Dependency Tree Display | Epic 8 | 4 |
| tskl-2ly | Migration from Beads | Epic 6 | 7 |
| tskl-l4q | User Documentation | - | 8 |
| tskl-nqs | Installation and Distribution | Epic 6 | 5 |
| tskl-34w | Polish and Quality Refinement | Epics 10-16 | 7 |

## Code Quality Standards

This project follows **behavior-driven development (BDD)** with strict quality requirements:

- 100% BDD spec coverage (Gherkin scenarios)
- Ruff + Black for Python formatting
- Clippy + rustfmt for Rust formatting
- Sphinx docstrings on every Python class/method
- Rustdoc comments on every Rust public item
- Spec parity checker ensures implementations stay in sync
- Long, descriptive names (no abbreviations)
- No line-level comments (code should be self-documenting)

See [AGENTS.md](AGENTS.md) for complete standards.

## Next Steps

1. **Start with Epic 0**: Set up repository structure, build files, CI pipeline
2. **Follow the BDD workflow**: Write Gherkin first, implement Python, implement Rust
3. **Run quality gates**: All checks must pass before merging
4. **Use bd commands**: All work is tracked in Beads

### Getting Started with Development

```bash
# Clone the repository
git clone https://github.com/AnthusAI/Taskulus.git
cd Taskulus

# View the next task to work on
bd ready

# Show details of a specific epic
bd show tskl-zqm

# View the dependency tree
bd graph tskl-zqm

# Start working on a task
bd update <task-id> --status in_progress --assignee "your@email.com"
```

## Documentation

- [VISION.md](planning/VISION.md) - Complete specification with examples
- [IMPLEMENTATION_PLAN.md](planning/IMPLEMENTATION_PLAN.md) - Detailed technical plan
- [AGENTS.md](AGENTS.md) - Code quality standards and workflow
- [GETTING_STARTED.md](GETTING_STARTED.md) - Setup and first steps
- [CLI_REFERENCE.md](CLI_REFERENCE.md) - CLI command reference
- [WIKI_GUIDE.md](WIKI_GUIDE.md) - Wiki authoring and rendering
- [CONFIGURATION.md](CONFIGURATION.md) - Project configuration format
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and fixes
- [MIGRATION.md](MIGRATION.md) - Migration from Beads

## Migration from Beads

Epic 14 includes a complete migration path from Beads to Taskulus:
- Parse Beads JSONL format
- Map fields to Taskulus schema
- Validate migrated data
- Comprehensive migration guide

## Contributing

We welcome contributions! Please:
1. Pick a task from `bd ready`
2. Follow the BDD workflow in [AGENTS.md](AGENTS.md)
3. Ensure all quality gates pass
4. Submit PR with spec parity verified

## License

MIT

## Inspiration

Taskulus is inspired by [Beads](https://github.com/steveyegge/beads) by Steve Yegge, but simplified:
- One JSON file per issue (not single JSONL file)
- In-memory index (not SQLite + daemon)
- Visible project/ directory (not hidden .beads/)
- Dual Python/Rust implementations
- Comprehensive BDD spec coverage

---

**Let's build a better project management tool.**
