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
  motionDurationMs = 240,
  motionEase = "power3.out",
  highlightOffsetY = -2
}: AnimatedSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({});

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
    const height = 24;

    const currentMotion = motionMode();
    const shouldAnimate = animate && currentMotion !== "off";

    if (!shouldAnimate) {
      gsap.set(highlight, { x: left, y: top, width, height, opacity: 1 });
      return;
    }

    const duration = currentMotion === "reduced" ? 0.12 : motionDurationMs / 1000;

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
        "relative isolate inline-flex items-center gap-3 rounded-full bg-[var(--column)] p-2 max-w-full h-8",
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
              "relative z-10 flex items-center gap-2 rounded-full px-2 py-1 text-xs font-semibold uppercase tracking-[0.2em] whitespace-nowrap h-7",
              "md:px-3",
              selected ? "text-foreground" : "text-muted",
              "max-md:px-1 max-md:gap-1 max-md:[&_span.selector-label]:hidden"
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
