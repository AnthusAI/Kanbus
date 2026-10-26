import type { ProjectConfig } from "../types/issues";

const RADIX_COLORS = new Set([
  "amber",
  "blue",
  "bronze",
  "brown",
  "crimson",
  "cyan",
  "gold",
  "grass",
  "gray",
  "green",
  "indigo",
  "iris",
  "jade",
  "lime",
  "mauve",
  "mint",
  "olive",
  "orange",
  "pink",
  "plum",
  "purple",
  "red",
  "ruby",
  "sage",
  "sand",
  "sky",
  "slate",
  "teal",
  "tomato",
  "violet",
  "yellow"
]);

const COLOR_ALIASES: Record<string, string> = {
  black: "gray",
  bright_black: "slate",
  grey: "gray",
  white: "gray",
  bright_white: "slate",
  red: "red",
  bright_red: "ruby",
  green: "green",
  bright_green: "grass",
  yellow: "amber",
  bright_yellow: "yellow",
  blue: "blue",
  bright_blue: "indigo",
  magenta: "purple",
  bright_magenta: "pink",
  cyan: "cyan",
  bright_cyan: "teal"
};

function normalizeColorValue(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
}

function resolveRadixColorName(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const normalized = normalizeColorValue(value);
  if (RADIX_COLORS.has(normalized)) {
    return normalized;
  }
  return COLOR_ALIASES[normalized] ?? null;
}

function buildRadixVariable(name: string, scale: string): string {
  return `var(--${name}-${scale})`;
}

export function resolveStatusCategoryColorName(
  config: ProjectConfig,
  statusKey: string
): string | null {
  const statusDef = config.statuses.find((status) => status.key === statusKey);
  const categoryColor =
    config.categories.find((category) => category.name === statusDef?.category)
      ?.color ?? null;
  return resolveRadixColorName(categoryColor ?? null);
}

export function buildStatusCategoryColorVariable(
  config: ProjectConfig,
  statusKey: string,
  scale: string
): string | null {
  const colorName = resolveStatusCategoryColorName(config, statusKey);
  if (!colorName) {
    return null;
  }
  return buildRadixVariable(colorName, scale);
}
