# Kanbus

**Track issues in your repository where your agents can participate.**

![Python CI](https://raw.githubusercontent.com/AnthusAI/Kanbus/badges/python-ci.svg)
![Rust CI](https://raw.githubusercontent.com/AnthusAI/Kanbus/badges/rust-ci.svg)
![Python Coverage](https://raw.githubusercontent.com/AnthusAI/Kanbus/badges/python-coverage.svg)
![Rust Coverage](https://raw.githubusercontent.com/AnthusAI/Kanbus/badges/rust-coverage.svg)
[![PyPI](https://img.shields.io/pypi/v/kanbus.svg)](https://pypi.org/project/kanbus/)
[![Crates.io](https://img.shields.io/crates/v/kanbus.svg)](https://crates.io/crates/kanbus)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Kanbus keeps issues, events, and wiki pages as ordinary files next to your code, so people and coding agents share one board that travels with the repository. There is no database to run and no service to sign up for.

## Quick start

```bash
pip install kanbus        # or: cargo install kanbus, or download kbs from GitHub Releases

kbs init                  # or: kanbus init
kbs create "Implement the login flow"
kbs list --status open
kbs show <id>
kbs commit                # commit board changes to git
```

[Building from source](docs/dev/building-from-source.md) covers developer installs, and [Getting Started](docs/GETTING_STARTED.md) walks through your first board.

## Three ways to run it

| | Local files | Files in the cloud | S3 and DynamoDB |
| --- | --- | --- | --- |
| Where the board lives | `project/` in your working tree | `project/` in a shared git repository | A private S3 bucket indexed by DynamoDB |
| Who writes to it | You and your agents | Everyone with a clone, plus CI and cloud sandboxes | Signed-in users of a web application, through the Kanbus API |
| Status | Stable | Early; live updates over MQTT are optional | Preview |

All three use the same issue format, configuration, workflows, and validation. [Getting Started](docs/GETTING_STARTED.md) compares them and has a guide for each.

## Why files

- **One issue per file.** Parallel edits by people and agents merge cleanly, and every issue has a stable path you can link to from GitHub.
- **Git is the history.** Branches, reviews, blame, and revert work on the board exactly as they do on code.
- **Familiar vocabulary.** Initiatives, epics, tasks, and sub-tasks are the Jira terms models already know, with a small core model of status, priority, and dependencies.
- **A wiki that reads the board.** Markdown pages render with live issue data, so planning documents reflect the real state of the project.
- **Agent provenance and WIP.** Writes can record which agent and model acted, and `kbs now` reinjects work in progress after an agent's context is compacted.

Kanbus is a spiritual successor to [Beads](https://github.com/steveyegge/beads). It drops the secondary SQLite index and single JSONL file in favor of plain files, and it can read and import Beads data. See [Kanbus vs. Beads](docs/VS_BEADS.md) and [Migrating from Beads](docs/MIGRATION.md).

## Two implementations

Kanbus ships a Python CLI (`kanbus`) and a Rust CLI (`kbs`, plus the `kbsc` console server). They are separate, complete implementations that run the same Gherkin behavior specifications in [`features/`](features), so commands, output, and file formats match. Python installs with `pip` and is the lighter dependency; Rust is faster on large boards.

The index daemon is opt-in: set `KANBUS_DAEMON=1` to let read-heavy commands use an automatically started daemon, and see `kbs daemon-status` and `kbs daemon-stop`. Without it, commands never start or wait for a background process.

## Console

`kbsc` serves a web board for the repository you run it in, on the `console_port` from `.kanbus.yml` or `http://127.0.0.1:5174/`. Prebuilt binaries embed the frontend, and `kbs console screenshot` captures the board as a PNG. See [Getting Started](docs/GETTING_STARTED.md) for installation and `./dev.sh` for development.

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [CLI reference](docs/CLI_REFERENCE.md) and [configuration](docs/CONFIGURATION.md), both generated from the code
- [Methodologies](docs/METHODOLOGIES.md): pluggable process guidance for your agents
- [Realtime collaboration](docs/REALTIME.md), [wiki guide](docs/WIKI_GUIDE.md), [lifecycle hooks](docs/LIFECYCLE_HOOKS.md)
- [Agent compaction and right-now summaries](docs/AGENT_COMPACTION_RIGHT_NOW.md); run `kbs setup ai` once to store an LLM key for AI features
- [Architecture](docs/ARCHITECTURE.md) and [troubleshooting](docs/TROUBLESHOOTING.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## License

MIT. Built by [Anthus AI Solutions](https://anth.us), who use Kanbus so agents and humans share one board.
