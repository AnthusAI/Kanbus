# One board for console and embedded applications

The canonical console imports `Board` from `@kanbus/ui`. `IssueCollection`
composes that **same Board**, BoardColumn and IssueCard; it is not a second
implementation. Papyrus, Prospectus and Cyclotron consumers supply configuration,
records, theme and transport adapters. No board markup is copied into consumers.

## Shared interaction contract

Board now owns column collapse without host callbacks. Headers work with pointer,
Enter and Space; status definitions accept `collapsed: true` defaults. Optional
`columnStateKey` persists state in a host-owned workspace/account namespace.
Omitting it gives an ephemeral board. Malformed/denied storage falls back to
configuration while controls remain usable. Read-after-mount keeps server and
first client markup consistent; preferences never mutate issue records/config.

The console's external agent/UI commands use the exported controller
`useBoardColumnState({config, storageKey})`, passing its `collapsedColumns` and
`toggleColumn` to Board. `setCollapsedColumns` supports functional updates.
Default/toggle/persistence logic lives in this module once, not in App.tsx.
Explicit controlled `collapsedColumns` requires `onToggleCollapse`; intentionally
read-only controlled state keeps disabled headers. Most hosts omit both props.

```tsx
<IssueCollection issues={records} config={config} query={query} view={view}
  selectedIssueId={selected?.id} onSelectIssue={setSelected}
  detailOpen={Boolean(selected)}
  columnStateKey={`my-app.columns.v1.${workspaceId}.${accountId}`} />
```

Existing CSS imports: tokens.css, kanban.css, optional organizer.css scoped by
`.kb-theme-organizer`. `IssueCollection.detailOpen` forwards actual detail
visibility to Board. React18/React19 are supported peers. Transport/auth stay
outside the component.

| Behavior | Shared owner / host boundary |
| --- | --- |
| Collapse/expand/defaults/persistence | Board + exported useBoardColumnState; no consumer toggle implementation |
| Sorting/counts/cards/FLIP/reduced motion/scrolling | Existing Board/BoardColumn/IssueCard, unchanged |
| Type filters | Shared IssueTypeFilter and configured type helpers; feeds IssueCollection.query or console route state |
| Hierarchy/workflow | Shared configured workflow/parent query helpers. Actual relationship commands remain backend-owned; console engineering view presets remain its existing navigation. |
| Selection/details | Shared card emits original typed record, supports Enter/Space. Generic IssueDetailPanel owns focus/Escape/close. Console's transport-aware TaskDetailPanel stays shared; hosts own route, placement and mutation adapter. |
| Mobile/keyboard | Native headers, focus and horizontal/touch scrolling, no alternate mobile board |
| View/filter/history preferences | Host router owns URL/list/wiki/hierarchy state. Shared column controller owns column preferences. |
| Drag/drop | No cross-column drag/drop exists in canonical Board or console. No unsupported mutation is presented as available. |

Default CSS motion honors system reduced motion. Hosts can explicitly choose
static/frame for actual playback needs; embedding alone is not a reason to force
static. Use IssueCollection.emptyMessage rather than a duplicate host message.

Regression: shared-board-state.feature covers standalone and embedded defaults,
keyboard/details, width/reload, malformed/denied storage at desktop/phone widths.
Existing query/type/organizer/motion cases remain. The actual console verifier
also checks collapse/defaults/reload/width/keyboard/selection and hierarchy/type
views. Papyrus verifies the packed, unmodified export in the running 8899 preview.

Local artifact pins are review checkpoints, not registry versions. A real
versioned release plus consumer lock update is required before production; never
ship a /tmp path as a production dependency. Cyclotron worktree is not edited.
