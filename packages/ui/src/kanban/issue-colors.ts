import type { CSSProperties } from "react";
import type { KanbanConfig, KanbanIssue } from "./types";

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

const LIGHT_ACCENT = "5";
const LIGHT_MUTED = "2";
const DARK_ACCENT = "8";
const DARK_MUTED = "3";
const PRIORITY_BG_LIGHT = "5";
const PRIORITY_BG_DARK = "8";
const STATUS_BG_LIGHT = "3";
const STATUS_BG_DARK = "7";

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

function resolveAccentColor(config: KanbanConfig, issue: KanbanIssue): string | null {
  const typeColor = config.type_colors[issue.type];
  const statusDef = config.statuses.find((status) => status.key === issue.status);
  const statusColor = statusDef?.color ?? null;
  const priorityColor = config.priorities[issue.priority]?.color ?? null;
  return resolveRadixColorName(typeColor ?? statusColor ?? priorityColor ?? null);
}

function resolvePriorityColor(config: KanbanConfig, issue: KanbanIssue): string | null {
  const priorityColor = config.priorities[issue.priority]?.color ?? null;
  return resolveRadixColorName(priorityColor);
}

function resolveStatusColor(config: KanbanConfig, statusKey: string): string | null {
  const statusDef = config.statuses.find((status) => status.key === statusKey);
  const categoryColor =
    config.categories.find((category) => category.name === statusDef?.category)
      ?.color ?? null;
  const statusColor = statusDef?.color ?? null;
  return resolveRadixColorName(statusColor ?? categoryColor ?? null);
}

export function buildIssueColorStyle(
  config: KanbanConfig,
  issue: KanbanIssue
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

export function buildStatusBadgeStyle(
  config: KanbanConfig,
  statusKey: string
): CSSProperties {
  const statusColor = resolveStatusColor(config, statusKey);
  const style: CSSProperties & Record<string, string> = {};

  if (statusColor) {
    style["--status-badge-bg-light"] = buildRadixVariable(statusColor, STATUS_BG_LIGHT);
    style["--status-badge-bg-dark"] = buildRadixVariable(statusColor, STATUS_BG_DARK);
  }

  return style;
}
