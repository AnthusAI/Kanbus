import React, { type CSSProperties, type ElementType, type ReactNode } from "react";

/** Ids of the editorial board themes. Each has a stylesheet at `@kanbus/ui/styles/themes/<id>.css`. */
export type KanbusThemeId = "refined-newsprint" | "newspaper-gothic" | "night-desk" | "broadsheet-green";

/** `system` follows the visitor's color scheme; `light` and `dark` force a mode. */
export type KanbusColorMode = "light" | "dark" | "system";

export interface KanbusThemeDefinition {
  readonly id: KanbusThemeId;
  readonly name: string;
  /** Human description of the font pairing and palette. */
  readonly pairing: string;
  readonly titleFace: string;
  readonly uiFace: string;
  readonly monoFace: string;
}

export const KANBUS_THEMES: readonly KanbusThemeDefinition[] = [
  {
    id: "refined-newsprint",
    name: "Refined Newsprint",
    pairing: "Source Serif 4 titles, IBM Plex Sans interface, IBM Plex Mono ids; warm paper, press red",
    titleFace: "Source Serif 4",
    uiFace: "IBM Plex Sans",
    monoFace: "IBM Plex Mono"
  },
  {
    id: "newspaper-gothic",
    name: "Newspaper Gothic",
    pairing: "Libre Franklin throughout, JetBrains Mono ids; cool paper, ink blue",
    titleFace: "Libre Franklin",
    uiFace: "Libre Franklin",
    monoFace: "JetBrains Mono"
  },
  {
    id: "night-desk",
    name: "Night Desk",
    pairing: "Literata titles, Public Sans interface, JetBrains Mono ids; slate, amber",
    titleFace: "Literata",
    uiFace: "Public Sans",
    monoFace: "JetBrains Mono"
  },
  {
    id: "broadsheet-green",
    name: "Broadsheet Green",
    pairing: "Newsreader titles, Hanken Grotesk interface, IBM Plex Mono ids; cream stock, deep green",
    titleFace: "Newsreader",
    uiFace: "Hanken Grotesk",
    monoFace: "IBM Plex Mono"
  }
];

export const DEFAULT_KANBUS_THEME: KanbusThemeId = "newspaper-gothic";

const GOOGLE_FONTS = "https://fonts.googleapis.com/css2?";

/** Google Fonts stylesheet URL per theme. The theme stylesheets make no requests: a host links
 * the URL for the theme it uses (for example in a `<link rel="stylesheet">`). */
export const KANBUS_THEME_FONTS: Readonly<Record<KanbusThemeId, string>> = {
  "refined-newsprint":
    `${GOOGLE_FONTS}family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap`,
  "newspaper-gothic":
    `${GOOGLE_FONTS}family=Libre+Franklin:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap`,
  "night-desk":
    `${GOOGLE_FONTS}family=Literata:opsz,wght@7..72,400;7..72,600&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap`,
  "broadsheet-green":
    `${GOOGLE_FONTS}family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Hanken+Grotesk:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap`
};

export function isKanbusThemeId(value: unknown): value is KanbusThemeId {
  return KANBUS_THEMES.some((theme) => theme.id === value);
}

/** The attributes a theme scope carries. `system` omits `data-color-mode` so the stylesheet follows
 * `prefers-color-scheme` (or a `.dark` ancestor). */
export function kanbusThemeAttributes(theme: KanbusThemeId, mode: KanbusColorMode = "system") {
  return {
    "data-kanbus-theme": theme,
    "data-color-mode": mode === "system" ? undefined : mode
  } as const;
}

export interface KanbusThemeScopeProps {
  theme: KanbusThemeId;
  mode?: KanbusColorMode;
  /** Overrides for public tokens, e.g. `{ "--kb-theme-accent": "oklch(0.5 0.15 30)" }`. */
  tokens?: Readonly<Record<`--kb-theme-${string}`, string>>;
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

/** Wraps a board in a themed scope. The host still imports the theme stylesheet and loads the fonts. */
export function KanbusThemeScope({ theme, mode = "system", tokens, as: Element = "div", className, style, children }: KanbusThemeScopeProps) {
  return (
    <Element {...kanbusThemeAttributes(theme, mode)} className={className} style={{ ...(tokens as CSSProperties), ...style }}>
      {children}
    </Element>
  );
}
