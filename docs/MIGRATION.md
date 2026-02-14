# Migration from Beads

Kanbus includes a migration path from Beads (JSONL format) to the Kanbus JSON-per-issue format. This guide explains the intended workflow and the field mapping.

## Summary

- Source: Beads JSONL file (one JSON object per line)
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
| id | id | Preserved when possible; otherwise regenerated with prefix |
| title | title | Required |
| body | description | Markdown preserved |
| type | type | Must exist in Kanbus config |
| status | status | Must be valid for the workflow |
| priority | priority | Converted to numeric priority |
| owner | assignee | String identifier |
| creator | creator | String identifier |
| parent | parent | Validated against hierarchy |
| tags | labels | Free-form labels |
| dependencies | dependencies | Converted to outbound links |
| comments | comments | Converted to Kanbus comment list |
| created_at | created_at | RFC3339 UTC |
| updated_at | updated_at | RFC3339 UTC |
| closed_at | closed_at | RFC3339 UTC or null |
| custom | custom | Preserved as key-value map |

## Validation and corrections

- Issues referencing missing parents or dependencies are rejected.
- Status values must exist in the configured workflow.
- Hierarchy violations must be corrected before import.
- If a Beads issue type does not exist in the Kanbus config, update the config first.

## After migration

- Run `kanbus validate` to check integrity.
- Review a sample of migrated issues in `project/issues/`.
- Commit the migrated files to git.

## Notes

Migration behavior will be finalized as part of Epic 14. This document will be updated when the command and exact flags are defined.
