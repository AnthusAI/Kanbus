# Organizer board theme and host integration

Use the exact shared package; hosts supply records, configuration and callbacks.
No component in this example fetches data, owns authentication or changes routes.

```tsx
import { IssueCollection, IssueDetailPanel, type KanbanIssue, type KanbanConfig } from '@kanbus/ui';
import '@kanbus/ui/styles/tokens.css';
import '@kanbus/ui/styles/kanban.css';
import '@kanbus/ui/styles/organizer.css';

<div className="kb-theme-organizer">
  <IssueCollection issues={issues} config={config} query={{type:'article'}}
    initialScroll="start" motion={{mode:'static'}} selectedIssueId={selected?.id}
    onSelectIssue={setSelected} columnStateKey="my-app.workspace-account.columns.v1"
    detailOpen={Boolean(selected)} />
  {selected && <IssueDetailPanel issue={selected} onClose={() => setSelected(null)}
    fields={[{label:'Owner', value:selected.assignee}]} />}
</div>
```

`IssueCollection` derives columns from `config.workflows` and `config.statuses`, filters issues with `query`, and passes the original typed record to `onSelectIssue`. Supply immutable issue arrays for host updates. The required `KanbanConfig` fields are `statuses`, `categories`, `priorities`, `type_colors`; `workflows` and `sort_order` are optional. Issue records require `id`, `title`, `type`, `status`, `priority`; other fields are optional. Use the exported types rather than copied interfaces.

`initialScroll` accepts `start`, `end` (the existing default), or `preserve`. It only controls initial positioning. Touch/horizontal scrolling remains native. Board owns collapse automatically; no host toggle callback is required. Optional `columnStateKey` persists configured column state in a host-owned workspace/account namespace. Status definitions accept `collapsed` for defaults. `detailOpen` forwards the actual detail visibility to Board. Cards without selection callbacks are noninteractive. With selection enabled, Enter/Space activates a card, and focus is visible. See [shared board behavior](SHARED_BOARD.md) for the single controller used by the canonical console and embedded consumers.

`IssueDetailPanel` requires `issue` and `onClose`. Optional `fields` is a readonly array of `{label:string,value:ReactNode}`; `children` supplies host editing or display content; `className` styles the shared surface. It displays ID, title, description and supplied fields. On mount it focuses its heading; on unmount it restores focus to the prior connected element. Escape and the Close button call the host callback. It is a nonmodal region; it does not trap focus. Hosts choose placement, width and responsive stacking. Existing transport-aware `TaskDetailPanel` is separate and is not needed for an offline island.

The optional `.kb-theme-organizer` scopes ivory/ink/cobalt colors, square outlined cards, folder headers and offset shadows. `data-color-mode="light"|"dark"` explicitly sets color mode; otherwise it follows the system (or a `.dark` ancestor). Hosts load licensed Geist/Jersey 10/Jersey 25 font assets themselves; the stylesheet makes no requests. Typography uses `--font-body`, `--kb-label-font`, `--kb-display-font`. Generic board tokens: `--kb-card-radius`, `--kb-column-radius`, `--kb-card-border`, `--kb-card-shadow`, `--kb-card-selected-shadow`, `--kb-board-gap`, `--kb-column-width`, `--kb-card-gap`. The default appearance is retained outside the theme scope. Essential board and panel geometry is included in `kanban.css`; Tailwind is not required. Avoid `styles/index.css` on a marketing page because its reset is page-wide.

Host playback owns its clock, immutable sample updates, narration and Pause/Replay/visibility controls. There is no timeline callback in the board. `motion.mode='css'` uses existing FLIP when issues move; `static` avoids it. Reduced-motion preference forces static shared transitions, including when changed at runtime. `frame` remains the existing deterministic entrance style; it is not a cross-column playback engine. GSAP is still statically imported by Board; measure the resulting island bundle rather than claiming animation-free tree shaking.

For Papyrus/Markus, inject a trusted publication-owned island mount through the build seam and bundle this package locally. Do not copy board DOM or serve CRM data. A client mount can retain a useful no-JavaScript explanation. If adding hydration later, server and browser must render identical initial data; do not hydrate markup produced by `renderToStaticMarkup`.

Acceptance: `features/organizer_theme.feature`, plus existing `features/issue_collection.feature`; `npm test` in this package runs the Cucumber browser fixtures with no transport.

## Newsprint theme

`import '@kanbus/ui/styles/newsprint.css'` after `kanban.css`, then put `data-kanbus-theme="newsprint"` on any ancestor of the board and detail panel. Columns are separated by one rule, cards by one rule, and every corner is square. The card's id and priority form a tight eyebrow directly above the headline. Selection is a left bar plus a heavier headline, never an inverted background. All text uses the full foreground color; light and dark (`data-color-mode`, a `.dark` ancestor, or the system preference) meet WCAG AA.

Host tokens, all optional: `--kb-newsprint-paper`, `--kb-newsprint-ink`, `--kb-newsprint-line`, `--kb-newsprint-display-font`, `--kb-newsprint-body-font`. The theme needs no `!important` overrides.

`KanbanIssue.excerpt` is an optional blurb. When present, the card shows it clamped to three lines with a More/Less toggle that does not select the card. Whether to pass a blurb or a subtitle is the host's decision.

Acceptance: `features/newsprint_theme.feature`. A Storybook story, "Themes/Newsprint board", shows both modes.
