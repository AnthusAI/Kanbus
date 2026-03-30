export function isConsoleDebugEnabled(flag?: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  const keys = [
    "kanbus.console.debug",
    flag ? `kanbus.console.${flag}` : null
  ].filter((key): key is string => Boolean(key));

  return keys.some((key) => window.localStorage.getItem(key) === "true");
}
