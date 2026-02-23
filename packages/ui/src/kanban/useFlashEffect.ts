import { useRef } from "react";

export function useFlashEffect<T>(_value: T, _enabled: boolean = true) {
  const elementRef = useRef<HTMLDivElement>(null);
  return elementRef;
}
