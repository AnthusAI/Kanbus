---
name: development-on-kanbus-console
description: >
  Closed-loop development workflow for Kanbus. Use this skill when making code
  changes to iterate independently: make changes, check logs, fix issues, repeat
  until working. Eliminates need to ask user for confirmation - logs tell you
  everything.
allowed-tools: "Bash(touch:*),Bash(ls:*),Bash(grep:*),Bash(kbs:*),Read"
version: "1.0.0"
author: "Kanbus Project"
license: "MIT"
---

# Kanbus Development Workflow

This skill provides a closed-loop development workflow that enables autonomous iteration on code changes without requiring user confirmation at each step.

## Overview

When making changes to Kanbus code, follow this workflow to verify your changes work correctly by checking logs yourself, identifying issues, and iterating until the feature is complete.

**Core Principle**: The logs tell you everything. Never ask the user "did it work?" - check `console.log` yourself.

## Prerequisites

Before starting development:

1. **ONE development server must be running**: `./dev.sh` from project root
   - **CRITICAL**: Only ONE instance of `./dev.sh` should run
   - **NEVER** manually run `kbsc` or `cargo run --bin kbsc` - let ./dev.sh manage it
   - Check: `ps aux | grep "dev.sh" | grep -v grep` (should show 1-2 processes)
   - If multiple kbsc processes exist: `pkill -9 kbsc` then verify ./dev.sh restarts it
2. **Console log file must exist**: `./console.log` in project root
3. **Browser should be open**: http://127.0.0.1:5174 (NOT 4242)

## Quick Command Reference

| Command | Purpose |
|---------|---------|
| `./dev.sh` | Start all watchers (UI, frontend, backend) |
| `kbs console reload` | Reload browser tab after frontend changes |
| `touch <file>` | Force Vite to detect file changes |
| `ls -lt apps/console/dist/assets/*.js \| head -1` | Verify build timestamp/hash changed |
| `grep '<pattern>' console.log \| jq ...` | Search logs for specific messages |
| `kbs <command>` | Execute CLI commands (create, comment, update, etc.) |

## The 7-Step Iteration Loop

### Step 1: Make Code Changes
- Edit the relevant source file(s)
- If Vite doesn't detect the change automatically: `touch <filename>`

### Step 2: Verify Build Updated
```bash
ls -lt apps/console/dist/assets/*.js | head -1
```
Check that:
- Timestamp is recent (within last minute)
- Filename hash changed (e.g., `index-abc123.js` → `index-def456.js`)

### Step 3: Reload Browser
```bash
kbs console reload
```
**Important**: Do NOT use `open <url>` - it opens a new browser window

### Step 4: Trigger Test Action
Execute the CLI command or user action that should trigger your feature:
```bash
kbs comment tskl-xxx "Test message"
# or
kbs update tskl-xxx --status in_progress
# or other relevant command
```

### Step 5: Check Logs
```bash
grep '"message":"\[FeatureName\]' console.log | jq -r '.at + " | " + .payload.message + " " + (.payload.args[1] | tostring)' | tail -20
```

Replace `[FeatureName]` with your console.log prefix (e.g., `[CommentAnimation]`).

### Step 6: Analyze and Iterate
- **If logs show expected behavior** → Feature works! Mark task complete.
- **If logs show unexpected behavior** → Analyze the issue, make a fix, go to Step 1.
- **If no logs appear** → Check if console.log statements exist in code, verify build updated, check telemetry connection.

### Step 7: Repeat Until Working
**Critical**: Continue iterating through Steps 1-6 until the feature works correctly. Do NOT ask the user "did it work?" or "should I continue?" - the logs provide all the information you need.

## Log File Format

The `console.log` file contains JSON objects with combined telemetry from:
- Browser `console.log/info/warn/error` statements
- CLI command output
- Server notifications

**Format**:
```json
{
  "type": "telemetry",
  "at": "2026-02-18T16:45:09.145Z",
  "payload": {
    "level": "info",
    "message": "[FeatureName] Action description",
    "args": ["[FeatureName] Action description", {"key": "value"}],
    "timestamp": "2026-02-18T16:45:09.145Z",
    "url": "http://localhost:4242/issues/tskl-xxx",
    "session_id": "abc123"
  }
}
```

**Extracting useful information**:
```bash
# Get message and first arg as JSON
jq -r '.payload.message + " " + (.payload.args[1] | tostring)' console.log

# With timestamps
jq -r '.at + " | " + .payload.message + " " + (.payload.args[1] | tostring)' console.log

# Filter by message pattern
grep '"message":"\[FeatureName\]' console.log | jq ...
```

## Common Issues and Solutions

### Vite Not Detecting Changes
**Symptom**: Build timestamp doesn't update after editing file
**Solution**: `touch <filename>` to force rebuild detection

### Old Code Still Running
**Symptom**: Changes don't appear in browser
**Solution**:
1. Check build timestamp updated: `ls -lt apps/console/dist/assets/*.js | head -1`
2. Reload browser: `kbs console reload`

### No Logs Appearing
**Symptom**: No console.log output in `console.log` file
**Solution**:
1. Verify console.log statements exist in your code
2. Check telemetry connection is active (look for `[notifications] connect` messages)
3. Ensure `./dev.sh` is running

### Port Conflicts / Multiple kbsc Instances
**Symptom**:
- Server fails to start (ports in use)
- Commands hang or timeout
- Error Code: -102 (connection refused)
- Multiple kbsc processes when checking: `ps aux | grep kbsc`

**Solution**:
1. Kill all kbsc: `pkill -9 kbsc`
2. Verify ./dev.sh is running: `ps aux | grep "dev.sh" | grep -v grep`
3. Wait 5 seconds for cargo-watch to restart kbsc automatically
4. **NEVER manually start kbsc** - let ./dev.sh handle it

## Development Server Details

`./dev.sh` runs three watchers:
1. **UI Styles Watcher** (packages/ui) - Copies CSS changes to dist/
2. **Frontend Watcher** (apps/console) - Rebuilds React app to dist/
3. **Rust Backend** (kbsc) - Auto-restarts console server on Rust changes

**Console URL**: http://127.0.0.1:5174 (NOT 4242 - that's the backend port)

## Real Example: Comment Animation Debugging

The MutationObserver approach was used to fix a DOM timing issue where React state showed N comments but DOM only had N-1 elements:

```
[CommentAnimation] Found comment elements {"count":88,"expected":89} ❌
→ Fixed by using MutationObserver to wait for DOM
[CommentAnimation] MutationObserver detected change {"count":89,"expected":89} ✓
```
