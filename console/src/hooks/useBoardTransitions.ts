import gsap from "gsap";
import { useLayoutEffect, useRef } from "react";

export function useBoardTransitions(dependencyKey: string) {
  const scope = useRef<HTMLDivElement | null>(null);
  const previousPositions = useRef<Map<string, DOMRect>>(new Map());

  useLayoutEffect(() => {
    if (!scope.current) {
      return;
    }

    const motion = document.documentElement.dataset.motion ?? "full";
    if (motion === "off") {
      return;
    }

    const cards = Array.from(
      scope.current.querySelectorAll<HTMLElement>(".issue-card")
    );

    const nextPositions = new Map<string, DOMRect>();
    for (const card of cards) {
      const issueId = card.dataset.issueId;
      if (!issueId) {
        continue;
      }
      nextPositions.set(issueId, card.getBoundingClientRect());
    }

    const duration = motion === "reduced" ? 0.2 : 0.35;
    const hasPrevious = previousPositions.current.size > 0;

    if (hasPrevious) {
      for (const card of cards) {
        const issueId = card.dataset.issueId;
        if (!issueId) {
          continue;
        }
        const previous = previousPositions.current.get(issueId);
        const next = nextPositions.get(issueId);
        if (!previous || !next) {
          continue;
        }
        const deltaX = previous.left - next.left;
        const deltaY = previous.top - next.top;
        if (deltaX === 0 && deltaY === 0) {
          continue;
        }
        gsap.fromTo(
          card,
          { x: deltaX, y: deltaY },
          { x: 0, y: 0, duration, ease: "power2.out", clearProps: "transform" }
        );
      }
    } else if (cards.length > 0) {
      gsap.fromTo(
        cards,
        { opacity: 0, y: 10 },
        {
          opacity: 1,
          y: 0,
          duration: motion === "reduced" ? 0.2 : 0.4,
          stagger: motion === "reduced" ? 0.01 : 0.03,
          ease: "power2.out"
        }
      );
    }

    previousPositions.current = nextPositions;
  }, [dependencyKey]);

  return scope;
}
