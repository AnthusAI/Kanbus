# Getting Started

This guide is a 10-minute walkthrough to initialize a Kanbus project, create and update issues, and learn basic queries. Kanbus is in the planning phase, so the commands below describe the intended workflow for the first release.

## Prerequisites

- Git
- Python 3.11+ or Rust toolchain

## Installation

Kanbus provides two **completely equivalent** CLI implementations plus a web console. All CLIs pass the same 100% specification test suite, use the same file formats, and provide the same commands. You can mix and match them within a team without issues.

### Option 1: Download Prebuilt Binaries (Recommended)

Download the latest release from [GitHub Releases](https://github.com/AnthusAI/Kanbus/releases):

**CLI Binary:**
```bash
# Linux x86_64
curl -L -o kanbus.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kanbus-x86_64-unknown-linux-gnu.tar.gz
tar -xzf kanbus.tar.gz
chmod +x kanbus
./kanbus --help

# macOS (choose your architecture)
curl -L -o kanbus.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kanbus-aarch64-apple-darwin.tar.gz  # Apple Silicon
curl -L -o kanbus.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kanbus-x86_64-apple-darwin.tar.gz   # Intel
```

**Console Server Binary:**
```bash
# Linux x86_64
curl -L -o kanbus-console.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kanbus-console-x86_64-unknown-linux-gnu.tar.gz
tar -xzf kanbus-console.tar.gz
chmod +x kanbus-console
./kanbus-console
# Opens web UI at http://127.0.0.1:5174/
```

### Option 2: Install from Package Managers

**Python** (pip) - Recommended for scripting and AI workflows:
```bash
pip install kanbus
```

**Rust** (cargo) - Recommended for max performance and CI/CD:
```bash
cargo install kanbus
```

The Rust installation includes both `kanbus` (CLI) and `kanbus-console` (web server).

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
