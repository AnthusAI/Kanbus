import type { CSSProperties } from "react";
import type { Issue, ProjectConfig } from "../types/issues";

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

const LIGHT_ACCENT = "5";
const LIGHT_MUTED = "2";
const DARK_ACCENT = "8";
const DARK_MUTED = "3";
const PRIORITY_BG_LIGHT = "5";
const PRIORITY_BG_DARK = "8";

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

function resolveAccentColor(config: ProjectConfig, issue: Issue): string | null {
  const typeColor = config.type_colors[issue.type];
  const statusDef = config.statuses.find((s) => s.name === issue.status);
  const statusColor = statusDef?.color ?? null;
  const priorityColor = config.priorities[issue.priority]?.color ?? null;
  return resolveRadixColorName(typeColor ?? statusColor ?? priorityColor ?? null);
}

function resolvePriorityColor(config: ProjectConfig, issue: Issue): string | null {
  const priorityColor = config.priorities[issue.priority]?.color ?? null;
  return resolveRadixColorName(priorityColor);
}

export function buildIssueColorStyle(
  config: ProjectConfig,
  issue: Issue
): CSSProperties {
  const accentColor = resolveAccentColor(config, issue);
  const priorityColor = resolvePriorityColor(config, issue);
  const style: CSSProperties & Record<string, string> = {};

  if (accentColor) {
    style["--issue-accent-light"] = buildRadixVariable(
      accentColor,
      LIGHT_ACCENT
    );
    style["--issue-accent-muted-light"] =
      buildRadixVariable(accentColor, LIGHT_MUTED);
    style["--issue-accent-dark"] = buildRadixVariable(
      accentColor,
      DARK_ACCENT
    );
    style["--issue-accent-muted-dark"] =
      buildRadixVariable(accentColor, DARK_MUTED);
  }

  if (priorityColor) {
    style["--issue-priority-bg-light"] = buildRadixVariable(
      priorityColor,
      PRIORITY_BG_LIGHT
    );
    style["--issue-priority-bg-dark"] = buildRadixVariable(
      priorityColor,
      PRIORITY_BG_DARK
    );
  }

  return style;
}
