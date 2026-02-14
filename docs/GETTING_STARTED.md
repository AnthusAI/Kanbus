# Getting Started

This guide is a 10-minute walkthrough to initialize a Kanbus project, create and update issues, and learn basic queries. Kanbus is in the planning phase, so the commands below describe the intended workflow for the first release.

## Prerequisites

- Git
- Python 3.11+ or Rust toolchain

## Installation

Kanbus provides two **completely equivalent** implementations. They pass the same 100% specification test suite, use the same file formats, and provide the same CLI commands. You can mix and match them within a team without issues.

<div style="display: flex; gap: 20px;">
  <div style="flex: 1; border: 1px solid #ddd; padding: 15px; border-radius: 8px;">
    <strong>Python</strong> (pip)<br>
    <em>Recommended for easy installation, scripting, and integrating with AI workflows.</em><br><br>
    <code>pip install kanbus</code>
  </div>
  <div style="flex: 1; border: 1px solid #ddd; padding: 15px; border-radius: 8px;">
    <strong>Rust</strong> (cargo)<br>
    <em>Recommended for max performance, large repositories, and CI/CD pipelines.</em><br><br>
    <code>cargo install kanbus</code>
  </div>
</div>

Python installs `kanbus`. Rust installs `kanbusr` with the same subcommands. You can switch between them at any time.

## Step 1: Initialize a project

Create a new repository or enter an existing one, then initialize Kanbus.

```bash
git init

kanbus init
```

You should now see:

```
project/
  config.yaml
  issues/
  wiki/
  .cache/   # created on demand
.kanbus.yml
```

If you want a local-only workspace for personal issues, initialize with:

```bash
kanbus init --local
```

That creates `project-local/` alongside `project/` and adds it to `.gitignore`.

## Step 1b: Keep agent guidance updated

Kanbus keeps agent instructions in sync with your configuration. Run this anytime the template or configuration changes.

```bash
kanbus setup agents
```

This updates `AGENTS.md`, refreshes `CONTRIBUTING_AGENT.md`, and re-writes the guard files under `project/`.

## Beads compatibility mode

If you are transitioning from Beads and keeping `.beads/issues.jsonl` for a while, enable compatibility mode in both configuration files:

```yaml
beads_compatibility: true
```

Set it in `.kanbus.yml` and in `project/config.yaml`. Kanbus will read Beads JSONL while still using `project/` for configuration and wiki content.

## Step 2: Create your first issue

```bash
kanbus create "Set up the project structure"
```

Kanbus returns a generated ID like `kanbus-a1b2c3`.

## Step 3: Update the issue

Move the issue into progress and assign it.

```bash
kanbus update kanbus-a1b2c3 --status in_progress --assignee "you@example.com"
```

## Step 4: Query issues

List all open issues:

```bash
kanbus list --status open
```

List issues that are ready to work on:

```bash
kanbus ready
```

Search by text:

```bash
kanbus search "project structure"
```

## Step 5: Close the issue

```bash
kanbus close kanbus-a1b2c3 --comment "Initial structure is complete."
```

## Running the specifications

Kanbus uses a shared Gherkin specification suite under the repository `features/` directory. Both implementations run against the same files.

Run the Python suite:

```bash
cd python
python -m behave
```

Run the Rust suite:

```bash
cd rust
cargo test --test cucumber
```

## Next Steps

- Read the CLI reference: [CLI_REFERENCE.md](CLI_REFERENCE.md)
- Configure workflows and types: [CONFIGURATION.md](CONFIGURATION.md)
- Learn the wiki system: [WIKI_GUIDE.md](WIKI_GUIDE.md)
- Troubleshoot common issues: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
