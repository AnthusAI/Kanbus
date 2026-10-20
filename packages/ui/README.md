# Shared Kanbus UI

`@kanbus/ui` supplies the same board, cards, and issue detail components used by
the standalone Kanbus console. Applications supply ordinary Kanbus issue types,
statuses, workflows, and colors. Domain types do not require a fork of the UI.
Column collapse, defaults and optional persistence are shared behavior;
see [the full board contract](SHARED_BOARD.md).

## Controlled collections

```tsx
import { IssueCollection, type IssueQuery, type KanbanConfig } from "@kanbus/ui";
import "@kanbus/ui/styles/tokens.css";
import "@kanbus/ui/styles/kanban.css";

const configuration: KanbanConfig = {
  statuses: [
    { key: "draft", name: "Draft", category: "Active" },
    { key: "review", name: "Editorial review", category: "Active" },
    { key: "published", name: "Published", category: "Done" }
  ],
  categories: [{ name: "Active" }, { name: "Done" }],
  priorities: { 1: { name: "High" }, 2: { name: "Normal" } },
  type_colors: { article: "blue" },
  workflows: {
    article: { draft: ["review"], review: ["published"], published: [] }
  }
};

const query: IssueQuery = {
  type: "article",
  assignee: "alex",
  fields: [{ field: "custom.review_by", operator: "lte", value: "2026-10-14" }]
};

<IssueCollection
  issues={issues}
  config={configuration}
  query={query}
  view="board"
  selectedIssueId={selectedIssue?.id}
  onSelectIssue={setSelectedIssue}
  emptyMessage="No matching articles"
/>;
```

Use `view="list"` for the same filtered records as a list of existing Kanbus
cards. The list preserves input order. The board uses the existing per-column
Kanbus sort rules. Supply immutable issue arrays when data changes.

The host owns fetching, authentication, navigation, mutations, and errors.
`IssueCollection` never fetches or changes a URL. Selection returns the original
record, including host-specific fields. Apply server-side tenant authorization
before supplying records; client filtering is not an authorization boundary.

`filterIssues(issues, query)` is also exported for host compositions. Its query
uses AND semantics for `type`, `status`, `assignee`, `label`, `parent`, `search`,
and `fields`. Standard scalar filters are exact; labels use membership; parent
accepts the existing Kanbus full ID or ID-prefix behavior. Search matches title,
description, and displayed comment text without case sensitivity. Summary
comments search their activity summary when present.

Each field predicate has `{ field, operator, value }`. Dot paths may address
ordinary issue fields or nested `custom` fields. Supported operators are `eq`,
`lt`, `lte`, `gt`, and `gte`. Equality preserves scalar types; ranges compare
numbers or strings of the same type. Booleans support equality only. Missing
fields, objects, arrays, and inherited properties never match. Date strings
should use a single normalized representation (for example UTC ISO timestamps)
if the host wants chronological string comparisons.

Filtering applies only to the supplied array. Do not use it to implement global
sorting, search, or completeness over one page from a remote query. Use the
backend's equivalent query and pagination contract for those operations.

`getStatusColumnsForIssueTypes(config, types)` returns configured columns in
configuration order, using the union of the selected types' workflows. An empty
type selection, or a configuration with no workflows, uses every configured
status. A type-specific workflow takes precedence over `default`; a missing
workflow for a selected type is an error. The collection also limits columns
when an explicit status filter is supplied.

## Styling and existing components

The package uses Tailwind utilities. Include the package's compiled JavaScript
in the host Tailwind content paths, for example
`./node_modules/@kanbus/ui/dist/**/*.js`. With a local package symlink, also
include its real `dist` path. Map these Tailwind colors to CSS variables:

```ts
colors: {
  background: "var(--background)", card: "var(--card)",
  "card-muted": "var(--card-muted)", frame: "var(--frame)",
  column: "var(--column)", foreground: "var(--text-foreground)",
  muted: "var(--text-muted)", selected: "var(--text-selected)",
  border: "var(--border)"
}
```

Give the board container a bounded height and `min-height: 0`. Import
`styles/kanban.css` for component styles. Editorial board themes (four palettes, each light and dark) live under `styles/themes/`; see [THEMES.md](THEMES.md). `styles/tokens.css` supplies optional
global defaults and theme selectors; hosts may provide their own variables
instead. `styles/index.css` includes body typography and page defaults, so it is
intended for a full Kanbus page rather than an embedded region.

`Board`, `BoardColumn`, `IssueCard`, and `TaskDetailPanel` and their prop types
remain exported. `TaskDetailPanel` includes a comment/activity view and accepts
mutation callbacks, but its existing history transport requests
`${apiBase}/issues/:id/events`; D2 rendering uses `/api/render/d2`. Hosts using
that panel must provide those routes. The new controlled collection does not
depend on the panel or either route.

## Browser acceptance tests

The package-local Gherkin specifications describe React behavior rather than
Python/Rust CLI behavior. They exercise the real components in a separate host,
including the unchanged standalone `Board` API.

```sh
npm ci
npm run build
npx playwright install chromium --only-shell
npm test
```

Set `PLAYWRIGHT_BROWSERS_PATH` consistently during installation and testing to
keep browser binaries in a chosen temporary directory. The test server binds
only to loopback and stops after the suite. It does not start `kbsc` or touch a
Kanbus project. `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` explicitly selects an
existing Chromium executable when supplied. The suite imports the built package
through its public exports and typechecks the host fixture before opening the
browser.
## Shared issue type control

`IssueTypeFilter` wraps the same `AnimatedSelector` used by the console toolbar
and filter sidebar. Supply the project's `hierarchy` and `types` configuration,
the controlled value (`all` or `type:<configured-key>`), and `onChange`.
`issueTypeFromFilter(value)` returns the exact type for `IssueCollection.query`.
Selecting All or repeating the active choice clears the type restriction.
Configured independent types precede hierarchy levels, each in configuration
order with duplicate keys removed. Labels remain readable
in a horizontally scrolling control on narrow screens. Import `kanban.css` for
standalone layout and styles. System reduced motion disables selector animation.

Console hosts may additionally supply `viewOptions` for their hierarchy navigation
groups. Exact configured types use a separate namespace and do not replace those
views. The selector owns no transport, authentication, history, or filtering:
hosts persist the selected key and compose it with the shared exact-type query.
