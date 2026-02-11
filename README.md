# Taskulus

**A little Jira for your repo.**

![Python CI](https://raw.githubusercontent.com/AnthusAI/Taskulus/badges/python-ci.svg)
![Rust CI](https://raw.githubusercontent.com/AnthusAI/Taskulus/badges/rust-ci.svg)
![Python Coverage](https://raw.githubusercontent.com/AnthusAI/Taskulus/badges/python-coverage.svg)
![Rust Coverage](https://raw.githubusercontent.com/AnthusAI/Taskulus/badges/rust-coverage.svg)

Taskulus is an **agent-native** project management system that lives in your git repository. It gives you the structure of Jira (issues, epics, workflows) with the simplicity of Markdown, all stored as JSON files alongside your code.

## Why Taskulus?

### 1. The Sleep Factor
Offload your mental context. Instead of keeping 15 different chat sessions and open loops in your head, tell your agent to "record the current state" into Taskulus. It's a permanent, searchable memory bank for your AI workforce.

### 2. Files are the Database
- **No SQL Server**: We build a fast in-memory index from your files.
- **No Daemon**: There is no background process to crash or manage.
- **No API**: Your agents read and write files directly (or use the simple CLI).

### 3. Concurrency Solved
Unlike other file-based systems that use a single JSONL file (guaranteeing merge conflicts), Taskulus stores **one issue per file**. This allows multiple agents and developers to work in parallel without blocking each other.

### 4. Jira + Confluence for Agents
Taskulus includes a **Wiki Engine** that renders Markdown templates with live issue data. Your planning documents always reflect the real-time state of the project, giving agents the "forest view" they often lack.

---

## Status: Planning Phase

This repository contains the complete vision, implementation plan, and task breakdown for building Taskulus. We are building it in public, using Taskulus (via Beads) to track itself.

## Quick Start

```bash
# Initialize a new project
tsk init

# Create an issue
tsk create "Implement the login flow"

# List open tasks
tsk list --status todo

# Show details
tsk show tsk-a1b
```

## Python vs Rust

We provide two implementations driven by the same behavior specification:

**Choose Python if:**
- You want easy `pip install` with no compilation
- You are scripting custom agent workflows

**Choose Rust if:**
- You need maximum performance (sub-millisecond queries)
- You have a massive repository (> 2000 issues)

## Project Structure

```
Taskulus/
|-- planning/
|   |-- VISION.md                  # Complete specification
|   `-- IMPLEMENTATION_PLAN.md     # Detailed technical plan
|-- specs/                         # Shared Gherkin feature files
|-- python/                        # Python implementation
|-- rust/                          # Rust implementation
|-- apps/                          # Public website (Gatsby)
`-- .beads/                        # Project task database
```

## Contributing

We welcome contributions! Please:
1. Pick a task from `bd ready` (we use Beads for bootstrapping).
2. Follow the BDD workflow in [AGENTS.md](AGENTS.md).
3. Ensure all quality gates pass.

## License

MIT
