# Project Management with Beads (Project Memory)

**What:** Workflow rules for keeping engineering work tracked in Beads (project memory).

**Applies to:** Any repo using the Project Management with Beads skill.

**Prerequisites:** Beads CLI (`bd`) installed and authenticated; ability to create/update Beads tasks.

**CRITICAL AGENT INSTRUCTION:** Never perform a `git commit` until the user explicitly tells you to do so. Changes are made to files only; commits are user-initiated only.

---

## Daily workflow
1) Choose or create the Beads task before coding; assign yourself and move it to *In Progress*.
2) Capture the goal and acceptance criteria in the task note.
3) Run `beads-skill sync` to ensure `.agent-skills/project-management-with-beads/SKILL.md` is present; run `beads-skill inject` so the pointer block stays in the chosen file (default `AGENTS.md`).
4) Install hooks if prompted: `bd hooks install` (or `bd install-hooks`) so Beads metadata is enforced on commits.

## While you work
- Log decisions, blockers, and useful links (PRs, designs) in the Beads task comments.
- If repo conventions allow, include the Beads task ID in branch names and PR titles for traceability.
- When pausing, leave a short handoff comment in the task describing current status and next steps.

## Before opening a PR
- Verify acceptance criteria are met and note the tests you ran.
- Update the Beads task with a concise summary and link to the PR/diff.
- Ensure Beads hooks pass locally (`bd sync` if needed).

## After merge / completion
- Move the task to Done/Closed.
- Add a final note with the merged PR link and any follow-up tasks created.
- Clean up local branches if appropriate.

## Commands refresher
- `beads-skill sync --repo <path>`: copy the skill into `.agent-skills/project-management-with-beads/SKILL.md`.
- `beads-skill inject --repo <path> --agents-file AGENTS.md`: add/update the managed pointer block.
- `bd hooks install` or `bd install-hooks`: install Beads git hooks.
- `bd sync`: sync local repo state with Beads.

## Landing the plane (end of session)
- Update the Beads task with status, remaining steps, and next actions.
- Commit/push only when explicitly approved by the user.
