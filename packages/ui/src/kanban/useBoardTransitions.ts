import { useLayoutEffect, useRef } from "react";

export function useBoardTransitions(dependencyKey: string, enabled: boolean) {
  const scope = useRef<HTMLDivElement | null>(null);
  
  // Disabled CSS animations temporarily to debug Flip bounce back issue.
  // The IntersectionObserver was adding classes that might have been interfering.

  return scope;
}
