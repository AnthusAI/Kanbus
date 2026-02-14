# Kanbus vs. Beads

Kanbus is a spiritual successor to [Beads](https://github.com/steveyegge/beads). We are huge fans of the domain-specific cognitive model that Beads pioneered—treating project management as a first-class citizen within the repo, alongside the code.

However, after using Beads extensively, we identified several architectural areas where the model could be improved for AI agents and distributed teams. This page details those differences.

## At a Glance

| Feature | Beads | Kanbus | Why it matters |
| :--- | :--- | :--- | :--- |
| **Database** | SQLite + JSONL | Files Only (JSON) | Removes synchronization friction; simpler for agents. |
| **Storage** | Monolithic `issues.jsonl` | One file per issue | Eliminates merge conflicts; allows parallel work. |
| **Concurrency** | "Exclusive Claim" model | Git Native (Branching) | Aligns with standard Git workflows. |
| **Complexity** | 130+ attributes | Core graph schema | Reduces context window pollution for AI. |
| **Language** | Go | Python + Rust | Dual implementation for scripting vs performance. |
| **Nomenclature** | Custom ("Beads") | Standard (Jira-like) | Leverages AI pre-training on standard terms. |

## 1. The Sync Friction

Beads uses a secondary SQLite database to maintain an index of issues, which acts as a cache. This requires a background daemon and constant synchronization between the SQLite state and the JSONL file on disk.

If you forget to sync, or if the daemon isn't running, you hit friction. You often encounter situations where you cannot push your code because the secondary database is out of sync with your changes.

**Example of the "Sync Friction" in Beads:**

```bash
$ git pull
Already up to date.
$ git push
❌ Error: Uncommitted changes detected

Before pushing, ensure all changes are committed. This includes:
  • bd JSONL updates (run 'bd sync')
  • any other modified files (run 'git status' to review)

Run 'bd sync' to commit these changes:

  bd sync

error: failed to push some refs to 'https://github.com/example/repo.git'
$ bd sync
Exporting beads to JSONL...
✓ Exported 0 issues
✓ .beads/issues.jsonl updated
```

**The Kanbus Solution:**
Kanbus removes the SQLite database entirely. It reads the JSON files directly. There is nothing to sync, nothing to export, and nothing to "forget" to run. The files on disk are the source of truth, always.

## 2. Concurrency & Merge Conflicts

Beads stores all issues in a single `issues.jsonl` file.

*   **The Problem:** If User A updates Task 1 and User B updates Task 2, they both modify the same file (`issues.jsonl`). When they try to merge, they get a conflict, even though they were working on completely unrelated tasks.
*   **The AI Impact:** When multiple AI agents are working on different tasks in parallel, a monolithic file guarantees they will block each other.

**The Kanbus Solution:**
Kanbus stores **one file per issue** (e.g., `issues/kanbus-123.json`, `issues/kanbus-124.json`). Git handles the merging naturally. Two people can edit different files without ever seeing a conflict.

## 3. Cognitive Overload

Beads has a very rich schema with over 130 attributes per issue. While powerful, this creates significant "context pollution" for AI coding assistants. When you feed the schema to an LLM, it has to process a lot of fields it will never use.

**The Kanbus Solution:**
We streamlined the schema to the absolute essentials required for a Jira-like graph:
*   Status
*   Priority
*   Type (Epic vs Task)
*   Dependencies (Parent/Child, Blocks/Blocked By)
*   Description

This focused model allows AI agents to spend their tokens on solving the problem, not navigating the tool.

## 4. Nomenclature

Beads introduces new terminology (e.g., "beads", "exclusive claims") that the user (and the AI) must learn.

**The Kanbus Solution:**
We use the standard vocabulary that every developer (and every LLM) already knows: **Epics**, **Tasks**, **Sub-tasks**. By aligning with the ubiquitous Jira model, we leverage the massive amount of pre-training that models already have about how project management works.

## 5. Scope & Privacy

Beads uses a complex system of "contributor roles" to handle local vs. shared tasks, which imposes opinions about why you might want private tasks. It also stores project-related data outside the project directory, which can be confusing.

**The Kanbus Solution:**
Kanbus leverages the existing Git model for scoping:
*   **Monorepo Support:** Run `kanbus list` at the root to see everything. Run it in a subfolder to see only that folder's tasks.
*   **Local Tasks:** Want private tasks that aren't shared? Just put them in a folder and add it to `.gitignore`. Kanbus will still index them for you locally, but they won't be committed.
*   **Simple Mental Model:** You don't need to learn a new permission system. You just use `.gitignore` like you do for everything else.
