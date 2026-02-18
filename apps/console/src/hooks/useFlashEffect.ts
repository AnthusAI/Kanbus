import { useEffect, useRef } from "react";
import gsap from "gsap";

/**
 * Hook that creates a subtle flash effect on an element when a value changes.
 *
 * @param value - The value to watch for changes
 * @param enabled - Whether the effect is enabled
 * @returns A ref to attach to the element that should flash
 */
export function useFlashEffect<T>(value: T, enabled: boolean = true) {
  const elementRef = useRef<HTMLDivElement>(null);
  const previousValueRef = useRef<T>(value);

  useEffect(() => {
    if (!enabled || !elementRef.current) return;

    // Skip flash on initial mount
    if (previousValueRef.current === value) {
      previousValueRef.current = value;
      return;
    }

    previousValueRef.current = value;

    // Subtle flash effect: brief highlight that fades out
    const element = elementRef.current;

    gsap.timeline()
      .to(element, {
        backgroundColor: "var(--color-accent-subtle, rgba(59, 130, 246, 0.15))",
        duration: 0.15,
        ease: "power2.out"
      })
      .to(element, {
        backgroundColor: "transparent",
        duration: 0.4,
        ease: "power2.inOut"
      });
  }, [value, enabled]);

  return elementRef;
}
