# Migration from Beads

Kanbus includes a migration path from Beads (JSONL format) to the Kanbus JSON-per-issue format. This guide explains the intended workflow and the field mapping.

## Summary

- Source: `.beads/issues.jsonl` (one JSON object per line)
- Destination: `project/issues/<id>.json` files
- Only one direction is stored for dependencies (outbound only)
- Validation is strict; invalid data must be corrected before import

## Planned workflow

1. Export or locate your Beads JSONL data file.
2. Run the Kanbus migration command (to be provided in Epic 14).
3. Review the migration report for errors and warnings.
4. Validate the resulting project with `kanbus validate`.

## Field mapping

The following table describes the intended mapping between Beads and Kanbus fields.

| Beads field | Kanbus field | Notes |
|-------------|----------------|-------|
| id | id | Preserved as-is |
| title | title | Required |
| description | description | Markdown preserved |
| issue_type | type | Must exist in Kanbus config |
| status | status | Must be valid for the workflow |
| priority | priority | Numeric priority retained |
| assignee | assignee | String identifier |
| created_by | creator | String identifier |
| owner | custom.beads_owner | Preserved in custom map |
| notes | custom.beads_notes | Preserved in custom map |
| acceptance_criteria | custom.beads_acceptance_criteria | Preserved in custom map |
| close_reason | custom.beads_close_reason | Preserved in custom map |
| dependencies | parent or dependencies | `type=parent-child` becomes `parent`; all other types become dependencies with `target=depends_on_id` and `type` preserved |
| comments | comments | Converted to Kanbus comment list |
| created_at | created_at | RFC3339 UTC |
| updated_at | updated_at | RFC3339 UTC |
| closed_at | closed_at | RFC3339 UTC or null |

## Validation and corrections

- Issues referencing missing parents or dependencies are rejected.
- Status values must exist in the configured workflow.
- Hierarchy violations must be corrected before import.
- If a Beads issue type does not exist in the Kanbus config, update the config first.
- Timestamps with offsets are normalized to UTC and serialized in RFC3339 Z format.

## After migration

- Run `kanbus validate` to check integrity.
- Review a sample of migrated issues in `project/issues/`.
- Commit the migrated files to git.

## Notes

Migration behavior will be finalized as part of Epic 14. This document will be updated when the command and exact flags are defined.
