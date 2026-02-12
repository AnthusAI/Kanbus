# GitHub Issue Sync

Epic 15 adds bidirectional sync between the Taskulus plan repository (issue JSON files under `project/issues/`) and GitHub Issues. Each GitHub issue must link back to the source JSON file so users can jump from the issue to the file in the repo.

## Link format and discovery

### Why blob URLs

GitHub does not support reliable relative links from issue bodies to repo files. The only reliable way to get a **clickable** link from an issue to a file is a **blob URL**:

- `https://github.com/OWNER/REPO/blob/BRANCH/path/to/file.json`
- Optional line or range: `#L10` or `#L10-L20`

The sync job builds this URL from the environment so it works in any fork or repo (no hardcoded URLs).

### Deriving the blob URL

1. **Repository:** From `GITHUB_REPOSITORY` (e.g. `AnthusAI/Taskulus`).
2. **Branch:** Default branch from `gh repo view --json defaultBranchRef` (then `.defaultBranchRef.name`), or fallback `main`.
3. **Relative path:** From repo root to the issue file, e.g. `project/issues/tsk-a1b2c3.json`. The project directory name comes from `.taskulus.yaml` (`project_dir`) or discovery; the path is `{project_dir}/issues/{identifier}.json`.

Example: `https://github.com/AnthusAI/Taskulus/blob/main/project/issues/tsk-a1b2c3.json`

### Body format for parsing

Each GitHub issue that corresponds to a Taskulus issue must include in its body:

1. **HTML comment (for parsing):** `<!-- taskulus-source: project/issues/tsk-abc.json -->`  
   The value is the relative path from repo root to the issue JSON file.

2. **Human-facing link (clickable):** A line such as `Taskulus source: [project/issues/tsk-abc.json](<blob-url>)` so the link is visible and clickable.

The sync script parses the body for the HTML comment to decide whether an issue already has a Taskulus source. When creating or updating an issue, it appends or updates this block so the link stays correct.

## Scope

- **In scope:** Issues under the shared project directory only (e.g. `project/issues/*.json`). Not `project-local/issues/` (gitignored).
- **Repo context:** Sync runs in a git repo that has a Taskulus project (`.taskulus.yaml` and the project directory). The script uses the same project discovery as the CLI.

## Running the sync

### In CI (GitHub Actions)

The workflow `.github/workflows/sync-github-issues.yml` runs the sync on a schedule and optionally on push to `main`. It uses the `gh` CLI with `GITHUB_TOKEN`.

### Locally (dry-run or live)

From the repository root (where `.taskulus.yaml` and `project/` live):

```bash
# Dry-run: report what would be created or updated, no API writes
python tools/sync_github_issues.py --dry-run

# Live: create/update GitHub issues and optionally create Taskulus issues from orphan GitHub issues
python tools/sync_github_issues.py
```

Requires the [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated (`gh auth login`). The script invokes `gh issue list`, `gh issue create`, `gh issue view`, and `gh issue edit` only; no direct GitHub API client.

## Bidirectional behavior

1. **Taskulus to GitHub:** For each `project/issues/{id}.json`, ensure a GitHub issue exists whose body contains the blob link (and the HTML comment). Create the issue if missing; if it exists but the body lacks the link, append or update the link block.
2. **GitHub to Taskulus:** List open GitHub issues; for each, check the body for the Taskulus source marker. If missing, create a new Taskulus issue (new ID, write `project/issues/{id}.json`), then update the GitHub issue body to add the blob link and marker. Title and description are copied from the GitHub issue into the new JSON.

## Optional: storing GitHub issue number

When the sync creates or finds a GitHub issue for a Taskulus issue, it can store the GitHub issue number in the issue JSON under `custom.github_issue_number`. That allows the next run to update the existing GitHub issue by number instead of searching by body. The script may implement this in a follow-up.
