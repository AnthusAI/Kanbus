# Kanbus Console

A Vite + React + Node console for viewing Kanbus issues as a realtime kanban board.

## Requirements

- Node 18+
- npm

## Development

```bash
cd console
npm install
npm run dev
```

- Client runs on `http://localhost:5173`
- Server runs on `http://localhost:5174`
- `CONSOLE_PROJECT_ROOT` must point to the `project/` directory

## Data Sources

The server executes `kanbus console snapshot` from the repo root to read:

- `project/config.yaml`
- `project/issues/*.json`

The server reads these files directly and exposes:

- `GET /api/config`
- `GET /api/issues`
- `GET /api/issues/:id`
- `GET /api/events` (SSE stream)

## Realtime Updates

The server watches the entire `project/` directory. Any change triggers a debounced reload (250ms), runs the CLI snapshot command, and emits the full snapshot over SSE. The client updates the board immediately after receiving the snapshot.

## UI Specs

Console UI scenarios live in `features/console/` and run via Cucumber.js with Playwright:

```bash
cd console
npm install
npm run test:ui
```

## View Modes

- Initiatives: only `initiative` issues
- Epics: only `epic` issues
- Tasks: `task` plus configured non-hierarchical types (for example `bug`, `story`, `chore`)
- Sub-tasks appear only after clicking a task-level issue

## Settings

The Settings panel controls:
- Mode: light, dark, or system
- Theme: neutral, cool, warm
- Motion: full, reduced, or off
- Typeface: sans, serif, mono

Settings are stored in local storage under `kanbus.console.appearance`.

## Notes

- System light/dark mode is automatic (`prefers-color-scheme`).
- Status columns use the `default` workflow ordering in `project/config.yaml`.
- No write operations are implemented yet; this console is read-only.
