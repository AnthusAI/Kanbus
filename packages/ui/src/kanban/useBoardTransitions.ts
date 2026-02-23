import { useLayoutEffect, useRef } from "react";

export function useBoardTransitions(dependencyKey: string, enabled: boolean) {
  const scope = useRef<HTMLDivElement | null>(null);
  const animatedIds = useRef<Set<string>>(new Set());
  const animatedCount = useRef(0);

  useLayoutEffect(() => {
    if (!enabled) {
      return;
    }

    const container = scope.current;
    if (!container) {
      return;
    }

    const motion = document.documentElement.dataset.motion ?? "full";
    if (motion === "off") {
      return;
    }

    const maxAnimated = 60;
    animatedIds.current.clear();
    animatedCount.current = 0;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) {
            continue;
          }
          const target = entry.target as HTMLElement;
          const issueId = target.dataset.issueId;
          if (!issueId) {
            continue;
          }
          if (animatedIds.current.has(issueId)) {
            continue;
          }
          if (animatedCount.current >= maxAnimated) {
            target.classList.remove("issue-animate-seed");
            observer.unobserve(target);
            continue;
          }
          animatedIds.current.add(issueId);
          animatedCount.current += 1;
          requestAnimationFrame(() => {
            target.classList.remove("issue-animate-seed");
            target.classList.add("issue-animate-in-up");
          });
          observer.unobserve(target);
        }
      },
      {
        root: null,
        threshold: 0.2
      }
    );

    const cards = Array.from(
      container.querySelectorAll<HTMLElement>(".issue-card")
    );
    cards.forEach((card) => {
      card.classList.add("issue-animate-seed");
      observer.observe(card);
    });

    return () => {
      observer.disconnect();
    };
  }, [dependencyKey, enabled]);

  return scope;
}
