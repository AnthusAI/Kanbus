# Local files

In this setup the board is a folder in your repository. The CLI reads and writes it directly, the console serves it on your machine, and nothing leaves the machine until you push. Start here even if you plan to share the board later: the [files in the cloud](cloud-files.md) guide picks up where this one ends.

You need Git and one Kanbus CLI. See [Install the CLI](../GETTING_STARTED.md#install-the-cli).

## 1. Initialize the board

From the root of a git repository (run `git init` first for a new one):

```bash
kbs init
```

This creates:

```
.kanbus.yml                     # board configuration: key, types, workflows, statuses
project/
  AGENTS.md
  issues/                       # one JSON file per issue
  events/                       # one JSON file per change (audit history)
  wiki/                         # Markdown wiki pages
.gitignore                      # adds project/.overlay/
.claude/settings.json           # stops coding agents from reading or editing issue JSON
.cursorignore                   # same, for Cursor
.vscode/settings.json           # hides issue and event JSON in VS Code
CONTRIBUTING_AGENT.template.md
```

Run every `kbs` command from the repository root, where `.kanbus.yml` lives.

## 2. Choose a project key and console port

Open `.kanbus.yml` and change two lines before you create any issues:

```yaml
project_key: acme       # every issue id starts with this, for example acme-72fcad
console_port: 4311      # the port kbsc serves this board on
```

Every new board starts with the key `kanbus`. Change it to something short and unique to this repository, so ids from different boards cannot be confused. To change it after issues exist, use `kbs rekey`.

Give each repository its own `console_port`. Left unset, every board uses 5174 and two consoles on one machine collide.

## 3. Decide what goes into git

`kbs init` ignores only the overlay cache. Add the console cache too, and decide whether to keep event history:

```gitignore
project/.overlay/
project/.cache/
# Optional: keep event history out of git (see below)
project/events/
```

Issues (`project/issues/`), the wiki (`project/wiki/`), and `.kanbus.yml` are the board, so commit them. Event files are an audit trail of every change. Committing them keeps that history with the repository, at the cost of one new file per change; ignoring them keeps your history clean, and Kanbus still records events locally. Pick one and use it in every repository; the Kanbus repository itself ignores them.

Commit the setup:

```bash
git add -A
git commit -m "Set up Kanbus"
```

## 4. Say who you are

Kanbus records an author on comments and events. It uses `KANBUS_USER`, then `USER`. Set it once for every project on the machine:

```bash
kbs setup env KANBUS_USER --value you@example.com
```

The value goes in `~/.kanbus.env`. A project `.env` or your shell environment overrides it.

## 5. Work with issues

```bash
kbs create "Launch the website" --type epic
# ID: acme-4e3b31

kbs create "Write the landing page" --parent acme-4e3b31
# ID: acme-aeec87

kbs update acme-aeec87 --status in_progress --assignee you@example.com
kbs comment acme-aeec87 "First draft is up for review."
kbs close acme-aeec87
```

Issue types follow the hierarchy in `.kanbus.yml`: initiative, epic, task (the default), and sub-task, plus the standalone types bug, story, and chore. Statuses follow the workflow, so an issue can only move along allowed transitions.

Find work:

```bash
kbs list                          # every issue, grouped by status
kbs list --status in_progress
kbs list --search "landing page"
kbs ready                         # open issues that nothing blocks
kbs show acme-aeec87              # full details and comments
```

When an AI agent creates or updates issues, it should tag them with `--agent-platform`, `--agent-model`, and `--agent-name`. People can ignore the reminder that `kbs create` prints about this.

## 6. Commit board changes

Kanbus writes files but never commits them. Commit issue changes whenever you commit code, or on their own:

```bash
kbs commit
```

`kbs commit` stages and commits `project/issues/` only. If you track `project/events/`, commit it yourself. Uncommitted board changes are the most common way boards drift, especially when agents do the editing, so make `kbs commit` part of every agent's finishing routine.

## 7. Open the console

```bash
kbsc
# Loaded console_port from config: 4311
```

Open `http://127.0.0.1:4311/` to see the board. The console reads the same files as the CLI and updates live when the CLI changes them on the same machine. The Python package does not include the console; install `kbs` and `kbsc` for it.

## 8. Set up coding agents

```bash
kbs setup agents
```

This writes Kanbus instructions into `AGENTS.md` and `CONTRIBUTING_AGENT.md` and refreshes the guard files that keep agents from editing issue JSON. Agents should use `kbs` for issues and may edit `project/wiki/` directly. Run it again after you change `.kanbus.yml`.

Kanbus's own guidance covers only the board. How your team writes specifications and uses branches comes from methodologies, and `bdd` and `git-flow` are on by default. To change them, list the ones you want under `methodologies` in `.kanbus.yml`, run `kbs methodology list` to see what is active, and read [Methodologies](../METHODOLOGIES.md) to write your own.

## Optional: a private board next to the shared one

```bash
kbs init --local
```

This adds `project-local/`, which is gitignored, for personal issues that never leave your machine. `kbs localize <id>` and `kbs promote <id>` move issues between the two.

## Optional: require a minimum CLI version

Add a file named `kanbus-version` at the repository root containing one version, such as `0.34.0`. Older CLIs then refuse to run board commands in that repository, so everyone reads and writes the same format.

## Next

- Share the board with a team or with agents in other sandboxes: [Files in the cloud](cloud-files.md).
- Change types, workflows, and statuses: [Configuration](../CONFIGURATION.md).
- Choose or write the process guidance agents follow: [Methodologies](../METHODOLOGIES.md).
