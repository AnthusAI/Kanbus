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

export interface KanbusThemeFontFamily {
  /** CSS family name used by the theme font stacks. */
  readonly family: string;
  /** Suggested npm package that provides the font files. */
  readonly package: string;
  /** Weights the theme uses. */
  readonly weights: readonly number[];
}

const SOURCE_SERIF = { family: "Source Serif 4", package: "@fontsource-variable/source-serif-4", weights: [400, 600] } as const;
const PLEX_SANS = { family: "IBM Plex Sans", package: "@fontsource/ibm-plex-sans", weights: [400, 500, 600] } as const;
const PLEX_MONO = { family: "IBM Plex Mono", package: "@fontsource/ibm-plex-mono", weights: [400, 500] } as const;
const FRANKLIN = { family: "Libre Franklin", package: "@fontsource-variable/libre-franklin", weights: [400, 500, 600, 700] } as const;
const JETBRAINS = { family: "JetBrains Mono", package: "@fontsource-variable/jetbrains-mono", weights: [400, 500] } as const;
const LITERATA = { family: "Literata", package: "@fontsource-variable/literata", weights: [400, 600] } as const;
const PUBLIC_SANS = { family: "Public Sans", package: "@fontsource-variable/public-sans", weights: [400, 500, 600] } as const;
const NEWSREADER = { family: "Newsreader", package: "@fontsource-variable/newsreader", weights: [400, 600] } as const;
const HANKEN = { family: "Hanken Grotesk", package: "@fontsource-variable/hanken-grotesk", weights: [400, 500, 600] } as const;

/** Font families each theme expects, with suggested @fontsource packages. This is metadata only:
 * nothing in @kanbus/ui fetches fonts, so the host bundles or serves them itself. */
export const KANBUS_THEME_FONTS: Readonly<Record<KanbusThemeId, readonly KanbusThemeFontFamily[]>> = {
  "refined-newsprint": [SOURCE_SERIF, PLEX_SANS, PLEX_MONO],
  "newspaper-gothic": [FRANKLIN, JETBRAINS],
  "night-desk": [LITERATA, PUBLIC_SANS, JETBRAINS],
  "broadsheet-green": [NEWSREADER, HANKEN, PLEX_MONO]
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
