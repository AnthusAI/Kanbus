# Troubleshooting

This guide lists common errors and how to resolve them.

## Git repository not found

**Symptom**

```
Error: not a git repository
```

**Cause**

`kanbus init` requires a git repository to exist in the current directory.

**Fix**

Initialize git, then retry:

```bash
git init
kanbus init
```

## Malformed JSON in an issue file

**Symptom**

```
Error: failed to parse issue file
```

**Cause**

An issue JSON file under `project/issues/` is not valid JSON or does not match the required schema.

**Fix**

- Open the referenced file in `project/issues/` and validate the JSON.
- Ensure required fields are present and match the schema in VISION.md.
- If the file is not recoverable, restore it from git history.

## Invalid workflow transition

**Symptom**

```
Error: invalid transition from 'open' to 'blocked' for type 'task'
```

**Cause**

The transition is not permitted by the workflow defined in `kanbus.yml`.

**Fix**

- Check the workflow rules in `kanbus.yml`.
- Use a valid intermediate status, or adjust the workflow definition.

## Corrupted or stale cache

**Symptom**

- Issue list is missing items
- Queries show outdated results
- Cache file cannot be parsed

**Cause**

The cache in `project/.cache/index.json` is stale or corrupted.

**Fix**

Delete the cache file; it will be rebuilt on the next command:

```bash
rm -f project/.cache/index.json
```

## Workflow or hierarchy validation failures

**Symptom**

```
Error: hierarchy violation
```

**Cause**

A parent-child relationship violates the configured hierarchy or a non-hierarchical type has children.

**Fix**

- Review the `hierarchy` and `types` settings in `kanbus.yml`.
- Update the issue to a valid parent or change the issue type.

## Still stuck

If you cannot resolve an issue, run `kanbus validate` to get a full integrity report and inspect the errors for additional context.
