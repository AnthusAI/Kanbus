# Getting Started

This guide is a 10-minute walkthrough to initialize a Taskulus project, create and update issues, and learn basic queries. Taskulus is in the planning phase, so the commands below describe the intended workflow for the first release.

## Prerequisites

- Git
- Python 3.11+ or Rust toolchain

## Installation

Taskulus provides two **completely equivalent** implementations. They pass the same 100% specification test suite, use the same file formats, and provide the same CLI commands. You can mix and match them within a team without issues.

<div style="display: flex; gap: 20px;">
  <div style="flex: 1; border: 1px solid #ddd; padding: 15px; border-radius: 8px;">
    <strong>Python</strong> (pip)<br>
    <em>Recommended for easy installation, scripting, and integrating with AI workflows.</em><br><br>
    <code>pip install taskulus</code>
  </div>
  <div style="flex: 1; border: 1px solid #ddd; padding: 15px; border-radius: 8px;">
    <strong>Rust</strong> (cargo)<br>
    <em>Recommended for max performance, large repositories, and CI/CD pipelines.</em><br><br>
    <code>cargo install taskulus</code>
  </div>
</div>

Both install the `tsk` command. You can switch between them at any time.

## Step 1: Initialize a project

Create a new repository or enter an existing one, then initialize Taskulus.

```bash
git init

tsk init
```

You should now see:

```
project/
  config.yaml
  issues/
  wiki/
  .cache/   # created on demand
.taskulus.yaml
```

## Step 2: Create your first issue

```bash
tsk create "Set up the project structure"
```

Taskulus returns a generated ID like `tsk-a1b2c3`.

## Step 3: Update the issue

Move the issue into progress and assign it.

```bash
tsk update tsk-a1b2c3 --status in_progress --assignee "you@example.com"
```

## Step 4: Query issues

List all open issues:

```bash
tsk list --status open
```

List issues that are ready to work on:

```bash
tsk ready
```

Search by text:

```bash
tsk search "project structure"
```

## Step 5: Close the issue

```bash
tsk close tsk-a1b2c3 --comment "Initial structure is complete."
```

## Next Steps

- Read the CLI reference: [CLI_REFERENCE.md](CLI_REFERENCE.md)
- Configure workflows and types: [CONFIGURATION.md](CONFIGURATION.md)
- Learn the wiki system: [WIKI_GUIDE.md](WIKI_GUIDE.md)
- Troubleshoot common issues: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
