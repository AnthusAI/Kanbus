export function formatIssueId(value: string): string {
  const dashIndex = value.indexOf("-");
  if (dashIndex <= 0) {
    return value;
  }
  const prefix = value.slice(0, dashIndex);
  const remainder = value.slice(dashIndex + 1);
  if (!remainder) {
    return value;
  }
  return `${prefix}-${remainder.slice(0, 6)}`;
}
