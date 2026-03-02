export function formatIssueId(value: string): string {
  const normalized = value.trim().replace(/\.$/, "");
  const dashIndex = normalized.indexOf("-");
  if (dashIndex <= 0) {
    return normalized;
  }
  const prefix = normalized.slice(0, dashIndex).toUpperCase();
  const remainder = normalized.slice(dashIndex + 1);
  if (!remainder) {
    return normalized;
  }
  return `${prefix}-${remainder.slice(0, 6)}`;
}
