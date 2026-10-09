export const DEFAULT_SHORT_ID_LENGTH = 4;

export const MIN_SHORT_ID_LENGTH = 1;

export const MAX_SHORT_ID_LENGTH = 32;

export function clampShortIdLength(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_SHORT_ID_LENGTH;
  }
  return Math.min(
    Math.max(Math.trunc(value), MIN_SHORT_ID_LENGTH),
    MAX_SHORT_ID_LENGTH
  );
}

function splitIdentifier(identifier: string): {
  key: string;
  base: string;
  suffix: string;
} {
  let key = "";
  let remainder = identifier;
  const dashIndex = identifier.indexOf("-");
  if (dashIndex > 0) {
    key = identifier.slice(0, dashIndex);
    remainder = identifier.slice(dashIndex + 1);
  }
  let base = remainder;
  let suffix = "";
  const dotIndex = remainder.indexOf(".");
  if (dotIndex >= 0) {
    base = remainder.slice(0, dotIndex);
    suffix = remainder.slice(dotIndex);
  }
  return { key, base, suffix };
}

function normalizedBase(identifier: string): string {
  const { base } = splitIdentifier(identifier);
  return base.replace(/-/g, "").toLowerCase();
}

function longestCommonPrefixLength(left: string, right: string): number {
  const limit = Math.min(left.length, right.length);
  let index = 0;
  while (index < limit && left[index] === right[index]) {
    index += 1;
  }
  return index;
}

/**
 * Build display widths for short IDs from the full identifiers in the
 * visible set. Only colliding groups are widened past the default length;
 * every rendered ID in the set is guaranteed unique.
 */
export function buildShortIdWidths(
  ids: Iterable<string>,
  defaultLen: number = DEFAULT_SHORT_ID_LENGTH
): Record<string, number> {
  const defaultLength = clampShortIdLength(defaultLen);
  const groups = new Map<string, Array<{ id: string; normalized: string }>>();
  for (const id of ids) {
    if (!id || /^\d+$/.test(id)) {
      continue;
    }
    const { key } = splitIdentifier(id);
    const normalized = normalizedBase(id);
    if (!normalized) {
      continue;
    }
    const groupKey = key.toLowerCase();
    const entries = groups.get(groupKey) ?? [];
    entries.push({ id, normalized });
    groups.set(groupKey, entries);
  }
  const widths: Record<string, number> = {};
  for (const entries of groups.values()) {
    entries.sort((left, right) =>
      left.normalized < right.normalized
        ? -1
        : left.normalized > right.normalized
          ? 1
          : 0
    );
    for (let index = 0; index < entries.length; index += 1) {
      const entry = entries[index];
      let width = defaultLength;
      if (index > 0) {
        width = Math.max(
          width,
          longestCommonPrefixLength(entry.normalized, entries[index - 1].normalized) + 1
        );
      }
      if (index + 1 < entries.length) {
        width = Math.max(
          width,
          longestCommonPrefixLength(entry.normalized, entries[index + 1].normalized) + 1
        );
      }
      width = Math.min(clampShortIdLength(width), entry.normalized.length);
      widths[entry.id] = width;
    }
  }
  return widths;
}

/**
 * Format one issue ID for display: lowercase, trimmed to the width derived
 * from the visible set (or the default length when no widths are supplied).
 * Dotted sub-ID suffixes are preserved; full IDs stay intact for links.
 */
export function formatIssueId(
  value: string,
  widths?: Record<string, number> | null,
  defaultLen: number = DEFAULT_SHORT_ID_LENGTH
): string {
  if (!value) {
    return value;
  }
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) {
    return trimmed;
  }
  const { key, base, suffix } = splitIdentifier(trimmed);
  const normalized = base.replace(/-/g, "").toLowerCase();
  if (!normalized) {
    return trimmed.toLowerCase();
  }
  const width = widths?.[trimmed] ?? clampShortIdLength(defaultLen);
  const truncated = normalized.slice(0, width);
  if (!key) {
    return `${truncated}${suffix.toLowerCase()}`;
  }
  return `${key.toLowerCase()}-${truncated}${suffix.toLowerCase()}`;
}

export interface ShortIdLengthConfig {
  beads_compatibility?: boolean;
  short_id_length?: number | null;
}

/**
 * Effective default short-ID length for a project configuration.
 * Beads compatibility implies the legacy 6-character width unless
 * short_id_length is set explicitly.
 */
export function effectiveShortIdLength(config: ShortIdLengthConfig | null | undefined): number {
  const explicit = config?.short_id_length;
  if (typeof explicit === "number" && Number.isFinite(explicit)) {
    return clampShortIdLength(explicit);
  }
  if (config?.beads_compatibility) {
    return 6;
  }
  return DEFAULT_SHORT_ID_LENGTH;
}

/**
 * Hyphen-insensitive short-ID matcher shared with the CLI: strips hyphens
 * from the candidate base, requires project-key equality when both sides
 * have a key, keeps dotted sub-ID suffixes exact, and never matches
 * all-digit candidates non-exactly.
 */
export function shortIdMatches(
  candidate: string,
  fullId: string
): boolean {
  if (candidate === fullId) {
    return true;
  }
  if (!candidate || !fullId) {
    return false;
  }
  if (/^\d+$/.test(candidate)) {
    return false;
  }
  const candidateParts = splitIdentifier(candidate);
  const fullParts = splitIdentifier(fullId);
  if (candidateParts.key && fullParts.key && candidateParts.key !== fullParts.key) {
    return false;
  }
  if (candidateParts.suffix !== fullParts.suffix) {
    return false;
  }
  let candidateNormalized = candidateParts.base.replace(/-/g, "").toLowerCase();
  const fullNormalized = fullParts.base.replace(/-/g, "").toLowerCase();
  // Hyphen-insensitive: a dash-less candidate may glue the project key to
  // the hash ("kanbusaaaabbbb" for "kanbus-aaaabbbb"); strip the glued key.
  if (!candidateParts.key && fullParts.key) {
    const glued = fullParts.key.replace(/-/g, "").toLowerCase();
    if (glued && candidateNormalized.startsWith(glued)) {
      candidateNormalized = candidateNormalized.slice(glued.length);
    }
  }
  if (!candidateNormalized) {
    return false;
  }
  return fullNormalized.startsWith(candidateNormalized);
}
