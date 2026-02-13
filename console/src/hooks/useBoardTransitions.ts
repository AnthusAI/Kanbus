import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef } from "react";

export function useBoardTransitions(dependencyKey: string) {
  const scope = useRef<HTMLDivElement | null>(null);

  useGSAP(
    () => {
      if (!scope.current) {
        return;
      }

      const motion = document.documentElement.dataset.motion ?? "full";
      if (motion === "off") {
        return;
      }

      const columns = scope.current.querySelectorAll(".kb-column");
      const cards = scope.current.querySelectorAll(".issue-card");

      const columnDuration = motion === "reduced" ? 0.2 : 0.5;
      const cardDuration = motion === "reduced" ? 0.2 : 0.4;
      const columnStagger = motion === "reduced" ? 0.02 : 0.08;
      const cardStagger = motion === "reduced" ? 0.01 : 0.03;

      gsap.fromTo(
        columns,
        { opacity: 0, y: 12 },
        {
          opacity: 1,
          y: 0,
          duration: columnDuration,
          stagger: columnStagger,
          ease: "power2.out"
        }
      );

      gsap.fromTo(
        cards,
        { opacity: 0, y: 10 },
        {
          opacity: 1,
          y: 0,
          duration: cardDuration,
          stagger: cardStagger,
          ease: "power2.out",
          delay: motion === "reduced" ? 0 : 0.1
        }
      );
    },
    { scope, dependencies: [dependencyKey] }
  );

  return scope;
}
