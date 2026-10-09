import { createContext, useContext } from "react";

/**
 * Width map from full issue ID to display width, derived from the visible
 * issue set by the data layer. `null` means no widths were provided and
 * formatters fall back to the default length.
 */
export const DisplayIdWidthsContext = createContext<Record<string, number> | null>(null);

export function useDisplayIdWidths(): Record<string, number> | null {
  return useContext(DisplayIdWidthsContext);
}
