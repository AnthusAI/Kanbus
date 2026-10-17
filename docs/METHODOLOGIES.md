# Methodologies

Kanbus core describes board mechanics: issue types, hierarchy, workflows and commands. How a team works around that board, such as how behavior is specified, how branches are used, or how code risk is kept down, is a methodology. Methodologies are Markdown documents that Kanbus assembles into the generated `CONTRIBUTING_AGENT.md`, so every agent working in the repository reads the same process.

Two methodologies are built in and active by default:

| Name | What it carries |
| --- | --- |
| `bdd` | Outside-in Behavior-Driven Design: specifications in Gherkin before code, and the coverage rules that go with them |
| `git-flow` | `develop` for continuous integration, `main` for releases, short-lived feature and hotfix branches, and board changes straight to `develop` |

## Choose methodologies

List them under `methodologies` in `.kanbus.yml`, in the order they should appear:

```yaml
methodologies:
  - bdd
  - git-flow
```

Leave the key out for the default `[bdd, git-flow]`. Use `methodologies: []` for core guidance only. Unknown or repeated names fail `kbs setup agents` and `kbs doctor` with a message that names the methodology.

Regenerate the agents file after changing the list:

```bash
kbs setup agents --force
```

`--force` replaces `CONTRIBUTING_AGENT.md`, so keep project-specific guidance in `AGENTS.md` or in a methodology of your own rather than editing the generated file.

## See what is active

```bash
kbs methodology list
```

```text
* bdd (built-in) Outside-in Behavior-Driven Design
* git-flow (built-in) Git Flow
```

`*` marks an active methodology and `-` a built-in that is not active. A project bundle shows its folder, for example `* crap (bundle methodologies/crap) CRAP Reduction`.

```bash
kbs methodology show git-flow
```

prints the guidance exactly as it will appear in `CONTRIBUTING_AGENT.md`, with the project's template variables filled in. It works for built-ins that are not active too, so you can read one before adopting it.

`kbs doctor` reports the active methodologies, fails when one cannot be loaded or rendered, and warns when `CONTRIBUTING_AGENT.md` no longer matches what the configuration generates.

## Write your own

A methodology is a folder in your repository with a `METHODOLOGY.md` inside:

```text
methodologies/
  crap/
    METHODOLOGY.md
    tools/
      crap-report
```

```markdown
---
name: crap
title: CRAP Reduction
description: Keep change risk low by pairing complexity with coverage.
tools:
  - name: report
    command: tools/crap-report
    purpose: Report the CRAP score of every Python function in files changed since the base branch, worst first.
---
## CRAP Reduction

Run the report before and after your change, and leave the functions you touched with a lower score.
```

The frontmatter takes `name` and `title` (both required), an optional `description`, and an optional list of `tools`. The body is Markdown rendered with the same template variables as `CONTRIBUTING_AGENT.md`, such as `{{ project_key }}` and `{{ initial_status }}`. Start the body with a second-level heading, because it is placed directly into the agents file.

List the folder with `path`, relative to the repository root, next to any built-ins:

```yaml
methodologies:
  - bdd
  - git-flow
  - path: methodologies/crap
```

A bundle can replace a built-in by declaring the same `name`. List the bundle in place of the built-in, not next to it:

```yaml
methodologies:
  - path: methodologies/house-bdd   # declares name: bdd
  - git-flow
```

Errors name the folder: a missing folder, a folder without `METHODOLOGY.md`, frontmatter that does not parse, and two methodologies with the same name all fail with the bundle path in the message.

## Ship tools with a methodology

Each entry under `tools` has a `name`, a `command` path inside the bundle folder, and a one-line `purpose`. Kanbus adds the tools to the end of the methodology's section in `CONTRIBUTING_AGENT.md` with the exact command to run:

```text
### CRAP Reduction tools

Run these from the repository root:

- `kbs methodology run crap report`: Report the CRAP score of every Python function in files changed since the base branch, worst first.
```

```bash
kbs methodology run crap report --threshold 20
```

The tool runs from the repository root. Arguments after the tool name pass through unchanged, and the environment variable `KANBUS_METHODOLOGY_DIRECTORY` holds the bundle folder so the tool can read its own files. Standard output is printed. A non-zero exit fails the command and shows the tool's output.

The command must be executable, and it cannot be absolute, empty, or leave the bundle folder with `..`. A tool name can appear once per bundle. Only configured methodologies can run tools, and the built-ins declare none.

This repository includes `methodologies/crap` as a working example: a CRAP score is cyclomatic complexity squared times the untested fraction cubed, plus complexity, and its report ranks the functions you changed by that score.
