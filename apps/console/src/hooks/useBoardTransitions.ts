import gsap from "gsap";
import { useLayoutEffect, useRef } from "react";

export function useBoardTransitions(dependencyKey: string) {
  const scope = useRef<HTMLDivElement | null>(null);
  const previousPositions = useRef<Map<string, DOMRect>>(new Map());
  const previousElements = useRef<Map<string, HTMLElement>>(new Map());

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
    const nextElements = new Map<string, HTMLElement>();
    for (const card of cards) {
      const issueId = card.dataset.issueId;
      if (!issueId) {
        continue;
      }
      nextPositions.set(issueId, card.getBoundingClientRect());
      nextElements.set(issueId, card);
    }

    const duration = motion === "reduced" ? 0.45 : 0.75;
    const hasPrevious = previousPositions.current.size > 0;

    if (hasPrevious) {
      const removedIds: string[] = [];
      for (const issueId of previousPositions.current.keys()) {
        if (!nextPositions.has(issueId)) {
          removedIds.push(issueId);
        }
      }
      const removeDuration = motion === "reduced" ? 0.75 : 1.2;
      const moveDelay = removedIds.length > 0 ? removeDuration * 0.6 : 0;

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
          {
            x: 0,
            y: 0,
            duration,
            ease: "power2.out",
            delay: moveDelay,
            clearProps: "transform"
          }
        );
      }
    } else if (cards.length > 0) {
      gsap.fromTo(
        cards,
        { opacity: 0, y: 10 },
        {
          opacity: 1,
          y: 0,
          duration: motion === "reduced" ? 0.35 : 0.6,
          stagger: motion === "reduced" ? 0.02 : 0.05,
          ease: "power2.out"
        }
      );
    }

    if (hasPrevious) {
      for (const [issueId, previousCard] of previousElements.current.entries()) {
        if (nextPositions.has(issueId)) {
          continue;
        }
        const previous = previousPositions.current.get(issueId);
        if (!previous) {
          continue;
        }
        const ghost = previousCard.cloneNode(true) as HTMLElement;
        ghost.style.position = "fixed";
        ghost.style.left = `${previous.left}px`;
        ghost.style.top = `${previous.top}px`;
        ghost.style.width = `${previous.width}px`;
        ghost.style.height = `${previous.height}px`;
        ghost.style.margin = "0";
        ghost.style.pointerEvents = "none";
        ghost.style.zIndex = "30";
        ghost.style.transformOrigin = "center";
        ghost.dataset.issueId = issueId;
        document.body.appendChild(ghost);
        const removeDuration = motion === "reduced" ? 0.75 : 1.2;
        gsap.fromTo(
          ghost,
          { opacity: 1, scale: 1 },
          {
            opacity: 0,
            scale: 0.85,
            duration: removeDuration,
            ease: "power2.inOut",
            onComplete: () => {
              ghost.remove();
            }
          }
        );
      }
    }

    previousPositions.current = nextPositions;
    previousElements.current = nextElements;
  }, [dependencyKey]);

  return scope;
}
