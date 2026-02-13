import React, { useEffect, useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { Issue } from "../types/issues";
import { Board } from "./Board";

interface TaskDetailPanelProps {
  task: Issue;
  subTasks: Issue[];
  columns: string[];
  priorityLookup: Record<number, string>;
  onClose: () => void;
}

export function TaskDetailPanel({
  task,
  subTasks,
  columns,
  priorityLookup,
  onClose
}: TaskDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backdropRef = useRef<HTMLDivElement | null>(null);
  const isClosingRef = useRef(false);

  useGSAP(
    () => {
      if (!panelRef.current) {
        return;
      }
      const motion = document.documentElement.dataset.motion ?? "full";
      if (motion === "off") {
        if (backdropRef.current) {
          gsap.set(backdropRef.current, { opacity: 1 });
        }
        gsap.set(panelRef.current, { x: 0, opacity: 1 });
        return;
      }
      const duration = motion === "reduced" ? 0.15 : 0.45;
      gsap.fromTo(
        panelRef.current,
        { x: 80, opacity: 0 },
        { x: 0, opacity: 1, duration, ease: "power2.out" }
      );
      if (backdropRef.current) {
        gsap.fromTo(
          backdropRef.current,
          { opacity: 0 },
          { opacity: 1, duration: motion === "reduced" ? 0.1 : 0.35, ease: "power1.out" }
        );
      }
    },
    { dependencies: [task.id] }
  );

  const handleClose = () => {
    if (isClosingRef.current) {
      return;
    }
    isClosingRef.current = true;
    const motion = document.documentElement.dataset.motion ?? "full";
    if (motion === "off") {
      isClosingRef.current = false;
      onClose();
      return;
    }
    const animations: gsap.core.Tween[] = [];
    const duration = motion === "reduced" ? 0.12 : 0.35;
    if (panelRef.current) {
      animations.push(
        gsap.to(panelRef.current, {
          x: 80,
          opacity: 0,
          duration,
          ease: "power2.in"
        })
      );
    }
    if (backdropRef.current) {
      animations.push(
        gsap.to(backdropRef.current, {
          opacity: 0,
          duration: motion === "reduced" ? 0.1 : 0.3,
          ease: "power1.in"
        })
      );
    }

    if (animations.length === 0) {
      onClose();
      return;
    }

    gsap
      .timeline({
        onComplete: () => {
          isClosingRef.current = false;
          onClose();
        }
      })
      .add(animations, 0);
  };

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleClose();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  return (
    <div className="fixed inset-0 z-50">
      <div
        ref={backdropRef}
        className="panel-backdrop absolute inset-0"
        onClick={handleClose}
      />
      <div
        ref={panelRef}
        className="absolute right-3 top-3 bottom-3 w-[min(720px,90vw)] rounded-3xl bg-card p-3"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
              Task detail
            </p>
            <h2 className="text-2xl font-semibold text-foreground">{task.title}</h2>
            <p className="text-sm text-muted">{task.id}</p>
          </div>
          <button
            className="rounded-full bg-card-muted px-3 py-3 text-xs font-semibold uppercase tracking-[0.2em] text-muted"
            onClick={handleClose}
            type="button"
          >
            Close
          </button>
        </div>
        <div className="mt-3">
          <h3 className="text-sm font-semibold uppercase tracking-[0.3em] text-muted">
            Sub-tasks
          </h3>
          {subTasks.length === 0 ? (
            <p className="mt-3 text-sm text-muted">
              No sub-tasks yet for this item.
            </p>
          ) : null}
          <div className="mt-3">
            <Board
              columns={columns}
              issues={subTasks}
              priorityLookup={priorityLookup}
              transitionKey={`${task.id}-${subTasks.length}`}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
