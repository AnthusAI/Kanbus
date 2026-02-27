function resolveTimeZone(value?: string | null): string {
  if (!value) {
    return "UTC";
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(new Date());
    return value;
  } catch (error) {
    return "UTC";
  }
}

export function formatTimestamp(value: string, timeZone?: string | null): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const resolvedTimeZone = resolveTimeZone(timeZone);
  const formatter = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: resolvedTimeZone,
    timeZoneName: "short"
  });
  const parts = formatter.formatToParts(date);
  const lookup = parts.reduce<Record<string, string>>((accumulator, part) => {
    if (part.type !== "literal") {
      accumulator[part.type] = part.value;
    }
    return accumulator;
  }, {});
  const timeZoneName = lookup.timeZoneName ?? resolvedTimeZone;
  return `${lookup.weekday}, ${lookup.month} ${lookup.day}, ${lookup.year} ${lookup.hour}:${lookup.minute} ${lookup.dayPeriod} ${timeZoneName}`;
}
