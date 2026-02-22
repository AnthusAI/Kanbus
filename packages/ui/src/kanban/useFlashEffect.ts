import { useEffect, useRef } from "react";
import gsap from "gsap";

export function useFlashEffect<T>(value: T, enabled: boolean = true) {
  const elementRef = useRef<HTMLDivElement>(null);
  const previousValueRef = useRef<T | undefined>(undefined);
  const isFirstRenderRef = useRef(true);

  useEffect(() => {
    if (!enabled || !elementRef.current) return;

    if (isFirstRenderRef.current) {
      isFirstRenderRef.current = false;
      previousValueRef.current = value;
      return;
    }

    if (previousValueRef.current === value) {
      return;
    }

    previousValueRef.current = value;

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
