---
name: git-flow
title: Git Flow
description: Long-lived main and develop branches, short-lived feature, release and hotfix branches, and release categories derived from issue types.
---
## Git Flow

Branches have fixed roles.

- `main` holds released code. Every commit on `main` is a release.
- `develop` integrates finished work. Pull requests target `develop` unless they are releases or hotfixes.
- Feature branches start from `develop` and return to it through a pull request.
- Release branches start from `develop`, stabilize a version, and merge to `main` and back to `develop`.
- Hotfix branches start from `main`, fix an urgent defect, and merge to `main` and back to `develop`.

Never commit directly to `main` or `develop`.
Name the Kanbus issue in the branch name or the pull request description so code stays linked to intent.
Branch naming, review and approval rules in this repository's AGENTS.md take precedence over this section.

## Semantic Release Alignment

Issue types map directly to release categories.

{% for mapping in semantic_release_mapping %}
- {{ mapping.type }} -> {{ mapping.category }}
{% endfor %}

Release notes are a record, not commentary.
