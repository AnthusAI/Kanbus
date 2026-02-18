import React, { useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { cn } from "../utils/cn";

export interface SelectorOption {
  id: string;
  label?: string;
  content?: React.ReactNode;
}

export interface AnimatedSelectorProps {
  options: SelectorOption[];
  value: string | null;
  onChange: (value: string) => void;
  className?: string;
  name: string;
  motionDurationMs?: number;
  motionEase?: string;
  highlightOffsetY?: number;
}

function motionMode(): string {
  return document.documentElement.dataset.motion ?? "full";
}

export function AnimatedSelector({
  options,
  value,
  onChange,
  className,
  name,
  motionDurationMs = 420,
  motionEase = "power3.out",
  highlightOffsetY = 0
}: AnimatedSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const lastWidthRef = useRef<number | null>(null);
  const resizeTweenRef = useRef<gsap.core.Timeline | gsap.core.Tween | null>(null);

  const applyCompactState = (compact: boolean, animate: boolean) => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    console.info("[selector] compact-state", {
      name,
      compact,
      animate
    });
    const motion = motionMode();
    const shouldAnimate = animate && motion !== "off";
    const duration = motion === "reduced" ? 0.2 : motionDurationMs / 1000;
    const labels = Array.from(container.querySelectorAll<HTMLElement>(".selector-label"));
    const options = Array.from(container.querySelectorAll<HTMLElement>(".selector-option"));
    const buttons = Array.from(container.querySelectorAll<HTMLElement>('button[role="tab"]'));

    const labelTargets = labels.map((label) => ({
      label,
      width: label.scrollWidth
    }));
    console.info("[selector] label-metrics", {
      name,
      labels: labelTargets.map(({ label, width }) => ({
        text: label.textContent ?? "",
        scrollWidth: width,
        maxWidth: getComputedStyle(label).maxWidth
      }))
    });

    const endGap = compact ? 4 : 8;
    const endPadding = compact ? 4 : 8;

    const endLabelVars = (width: number) =>
      compact
        ? { maxWidth: 0, x: -4 }
        : { maxWidth: width, x: 0 };

    if (shouldAnimate) {
      if (resizeTweenRef.current) {
        resizeTweenRef.current.kill();
      }
      const timeline = gsap.timeline({
        defaults: { duration, ease: motionEase, overwrite: true },
        onUpdate: () => setHighlight(false),
        onComplete: () => setHighlight(false)
      });
      labelTargets.forEach(({ label, width }) => {
        timeline.to(label, { ...endLabelVars(width) }, 0);
      });
      options.forEach((option) => {
        timeline.to(option, { gap: endGap }, 0);
      });
      buttons.forEach((button) => {
        timeline.to(button, { paddingLeft: endPadding, paddingRight: endPadding }, 0);
      });
      resizeTweenRef.current = timeline;
    } else {
      labelTargets.forEach(({ label, width }) => {
        gsap.set(label, endLabelVars(width));
      });
      options.forEach((option) => {
        gsap.set(option, { gap: endGap });
      });
      buttons.forEach((button) => {
        gsap.set(button, { paddingLeft: endPadding, paddingRight: endPadding });
      });
      setHighlight(false);
    }

  };

  const setHighlight = (animate: boolean) => {
    const container = containerRef.current;
    const highlight = highlightRef.current;
    const target = value ? buttonRefs.current[value] : null;
    if (!container || !highlight || !target) {
      if (highlight) {
        gsap.set(highlight, { opacity: 0 });
      }
      return;
    }

    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const left = targetRect.left - containerRect.left;
    const top = targetRect.top - containerRect.top + highlightOffsetY;
    const width = targetRect.width;
    const height = 22;

    const currentMotion = motionMode();
    const shouldAnimate = animate && currentMotion !== "off";
    gsap.killTweensOf(highlight);

    if (!shouldAnimate) {
      gsap.set(highlight, { x: left, y: top, width, height, opacity: 1, overwrite: true });
      return;
    }

    let duration = motionDurationMs / 1000;
    if (currentMotion === "reduced") {
      duration = 0.2;
    }

    gsap.to(highlight, {
      x: left,
      y: top,
      width,
      height,
      opacity: 1,
      duration,
      ease: motionEase,
      overwrite: true
    });
  };

  useLayoutEffect(() => {
    setHighlight(false);
  }, []);

  useLayoutEffect(() => {
    setHighlight(true);
  }, [value]);

  useLayoutEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const media = window.matchMedia("(max-width: 768px)");
    applyCompactState(media.matches, false);
    const handler = (event: MediaQueryListEvent) => {
      console.info("[selector] media-change", {
        name,
        matches: event.matches
      });
      applyCompactState(event.matches, true);
      setHighlight(true);
    };
    media.addEventListener("change", handler);
    return () => {
      media.removeEventListener("change", handler);
    };
  }, [options]);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    let frame = 0;
    const schedule = () => {
      if (frame) {
        cancelAnimationFrame(frame);
      }
      frame = requestAnimationFrame(() => {
        const width = container.getBoundingClientRect().width;
        lastWidthRef.current = width;
        setHighlight(false);
      });
    };
    const observer = new ResizeObserver(() => {
      schedule();
    });
    observer.observe(container);
    Object.values(buttonRefs.current).forEach((button) => {
      if (button) {
        observer.observe(button);
      }
    });
    window.addEventListener("resize", schedule);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", schedule);
      if (frame) {
        cancelAnimationFrame(frame);
      }
    };
  }, [options]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative isolate inline-flex items-center gap-1 rounded-full bg-[var(--column)] p-1 max-w-full h-7 overflow-hidden",
        "md:max-w-none",
        className
      )}
      role="tablist"
      aria-label={name}
      data-selector={name}
    >
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div
          ref={highlightRef}
          className="selector-highlight absolute left-0 rounded-full h-6"
        />
      </div>
      {options.map((option) => {
        const selected = option.id === value;
        return (
          <button
            key={option.id}
            ref={(node) => {
              buttonRefs.current[option.id] = node;
            }}
            role="tab"
            aria-selected={selected}
            data-selector={name}
            data-option={option.id}
            className={cn(
              "relative z-10 flex items-center gap-1 rounded-full px-1.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] whitespace-nowrap h-7",
              "md:px-2",
              selected ? "text-foreground" : "text-muted",
              ""
            )}
            onClick={() => onChange(option.id)}
            type="button"
          >
            {option.content ?? option.label}
          </button>
        );
      })}
    </div>
  );
}
