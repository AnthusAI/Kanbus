# Getting Started

This guide is a 10-minute walkthrough to initialize a Kanbus project, create and update issues, and learn basic queries. Kanbus is in the planning phase, so the commands below describe the intended workflow for the first release.

## Prerequisites

- Git
- Python 3.11+ or Rust toolchain

## Installation

Kanbus provides two **completely equivalent** implementations: Python and Rust. Both pass the same 100% specification test suite, use the same file formats, and provide the same CLI commands. You can mix and match them within a team without issues.

<div style="display: flex; gap: 20px;">
  <div style="flex: 1; border: 1px solid #ddd; padding: 15px; border-radius: 8px;">
    <strong>Python</strong> (pip)<br>
    <em>Recommended for easy installation and scripting.</em><br><br>
    <code>pip install kanbus</code>
  </div>
  <div style="flex: 1; border: 1px solid #ddd; padding: 15px; border-radius: 8px;">
    <strong>Rust</strong> (cargo)<br>
    <em>Recommended for max performance and CI/CD pipelines.</em><br><br>
    <code>cargo install kanbus</code>
  </div>
</div>

Python installs `kanbus`. Rust installs `kbs` with the same subcommands. You can switch between them at any time.

## Prebuilt binaries

GitHub Releases include prebuilt binaries for the Kanbus Rust CLI and the Rust console server:

- `kbs` (CLI)
- `kbsc` (console server)

Download the archive for your platform (for example `kbs-<target>.tar.gz` and `kbsc-<target>.tar.gz`), unzip it, and place the binary on your PATH.

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

## Console (Rust backend)

### Development Mode (Recommended)

For development with automatic rebuilds on file changes:

```bash
./dev.sh
```

This single command starts:
- Frontend watcher (automatically rebuilds React/Vite on changes)
- Rust backend with auto-restart (restarts on Rust source changes)

The console will be available at `http://127.0.0.1:5174/`

Press `Ctrl+C` to stop all services.

### Production Build

For a one-time build of the console:

```bash
cd apps/console
npm install
npm run build
```

Then run the backend:

```bash
cargo run --bin console_local --manifest-path rust/Cargo.toml
```

### Console URLs

Local mode (default):
```
http://127.0.0.1:5174/
```

Multi-tenant mode (set `CONSOLE_TENANT_MODE=multi`):
```
http://127.0.0.1:5174/<account>/<project>/
```

### Environment Variables

- `CONSOLE_PORT` (default `5174`)
- `CONSOLE_ROOT` (sets both data root and assets root)
- `CONSOLE_DATA_ROOT` (data root override)
- `CONSOLE_ASSETS_ROOT` (assets root override)
- `CONSOLE_TENANT_MODE=multi` (enable `/account/project` mapping under data root)

## Install from source

Prerequisites for a fresh clone:

- Git
- Rust toolchain (stable)
- Node.js 20+ with npm

Clone the repository:

```bash
git clone https://github.com/AnthusAI/Kanbus.git
cd Kanbus
```

Install dependencies:

```bash
cargo build --manifest-path rust/Cargo.toml
cd apps/console && npm install && cd ../..
```

Run in development mode (with auto-rebuild on file changes):

```bash
./dev.sh
```

Then open:

```
http://127.0.0.1:5174/
```

(Or `http://127.0.0.1:5174/<account>/<project>/` if using multi-tenant mode with `CONSOLE_TENANT_MODE=multi`)

## Next Steps

- Read the CLI reference: [CLI_REFERENCE.md](CLI_REFERENCE.md)
- Configure workflows and types: [CONFIGURATION.md](CONFIGURATION.md)
- Learn the wiki system: [WIKI_GUIDE.md](WIKI_GUIDE.md)
