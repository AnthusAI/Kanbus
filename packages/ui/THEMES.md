# Editorial board themes

Four opt-in themes style `Board`, `IssueCollection` and the detail panels as flat, ruled newsroom boards. Each has a light and a dark mode.

| id | Name | Titles | Interface | Ids | Accent |
| --- | --- | --- | --- | --- | --- |
| `refined-newsprint` | Refined Newsprint | Source Serif 4 | IBM Plex Sans | IBM Plex Mono | press red |
| `newspaper-gothic` | Newspaper Gothic | Libre Franklin | Libre Franklin | JetBrains Mono | ink blue |
| `night-desk` | Night Desk | Literata | Public Sans | JetBrains Mono | amber |
| `broadsheet-green` | Broadsheet Green | Newsreader | Hanken Grotesk | IBM Plex Mono | deep green |

## Adopting a theme

```tsx
import { IssueCollection, KanbusThemeScope } from "@kanbus/ui";
import "@kanbus/ui/styles/tokens.css";
import "@kanbus/ui/styles/kanban.css";
import "@kanbus/ui/styles/themes/refined-newsprint.css"; // pulls in editorial-base.css

// Bundle the theme fonts yourself (see KANBUS_THEME_FONTS for families and @fontsource packages).
<KanbusThemeScope theme="refined-newsprint" mode="system">
  <IssueCollection issues={issues} config={config} query={{ type: "article" }} />
</KanbusThemeScope>
```

Without React, set the attributes directly: `data-kanbus-theme="refined-newsprint"` on any ancestor of the board and, to force a mode, `data-color-mode="light" | "dark"`. Omit `data-color-mode` to follow `prefers-color-scheme` (or a `.dark` ancestor). The console puts both attributes on `<html>`.

`KANBUS_THEMES` lists ids, display names, font pairing and face names; `KanbusThemeId` is the id union. `styles/themes/index.css` imports all four themes. The stylesheets make no requests: hosts bundle the fonts; `KANBUS_THEME_FONTS` lists, per theme, the family names, weights and suggested `@fontsource` packages.

## Public tokens

Each theme sets these on `[data-kanbus-theme="<id>"]` (dark values under `data-color-mode="dark"`). Override any of them on the scope element, inline or with `tokens` on `KanbusThemeScope`.

- Colors: `--kb-theme-paper`, `-panel`, `-sidebar`, `-ink`, `-muted`, `-rule`, `-accent`, `-on-accent`
- Fonts: `--kb-theme-title-font`, `-ui-font`, `-mono-font`
- Scale: `--kb-theme-title-size`, `-title-leading`, `-title-tracking`, `-heading-size`, `-heading-leading`, `-heading-tracking`, `-heading-weight`, `-reading-size`, `-reading-leading`, `-label-weight`

`styles/themes/editorial-base.css` maps these onto the base tokens (`--background`, `--card`, `--text-foreground`, `--text-muted`, `--text-selected`, `--font-body`) and the `--kb-*` geometry, and holds all structural rules. Every ink, muted, accent and on-accent pair meets WCAG AA (4.5 to 1) in both modes; overriding colors is the host's responsibility to keep that true.

## Migrating from `newsprint`

The `newsprint` theme and `--kb-newsprint-*` tokens are removed. Replace `data-kanbus-theme="newsprint"` with one of the ids above, import `@kanbus/ui/styles/themes/<id>.css` instead of `styles/newsprint.css`, and map any host overrides onto `--kb-theme-*` tokens.
