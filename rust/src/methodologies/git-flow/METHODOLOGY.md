---
name: git-flow
title: Git Flow
description: develop for continuous integration, main for releases, short-lived feature and hotfix branches, board changes straight to develop, and release categories derived from issue types.
---
## Git Flow

Branches have fixed roles.

- `develop` is the continuous-integration branch. Merge accepted, green work there as soon as it is ready.
- `main` is the release branch. Releases, including semantic-release, run only from `main`. A merge to `develop` is not a production release.
- Feature branches start from `develop` and return to it through a pull request. They are short-lived: do not park completed work on a feature branch waiting for `main`.
- Promote `develop` to `main` when you intend a release, not as the daily integration path.
- Hotfix branches start from `main`, fix an urgent defect, and merge to `main` and back to `develop`.

Open pull requests against `develop` for product work. Merge them there as soon as review is addressed and CI is green.

Project management does not need a pull request. Kanbus issues, comments, status changes and `project/wiki` pages are committed on `develop` and pushed, with no feature branch, pull request or review loop. Do not mix board files into a product pull request; land the board on `develop` first.

Never commit product code directly to `main` or `develop`.
Name the Kanbus issue in the branch name or the pull request description so code stays linked to intent.
Branch naming, review, release and approval rules in this repository's AGENTS.md take precedence over this section.

## Semantic Release Alignment

Issue types map directly to release categories.

{% for mapping in semantic_release_mapping %}
- {{ mapping.type }} -> {{ mapping.category }}
{% endfor %}

Release notes are a record, not commentary.
