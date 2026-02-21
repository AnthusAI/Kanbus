import React, { useEffect, useRef, useState } from "react";
import { Check, FolderOpen, X } from "lucide-react";
import gsap from "gsap";

interface ProjectFilterPanelProps {
  isOpen: boolean;
  onClose: () => void;
  projectLabels: string[];
  enabledProjects: ReadonlySet<string>;
  onToggleProject: (label: string) => void;
  hasLocalIssues: boolean;
  showLocal: boolean;
  showShared: boolean;
  onToggleLocal: () => void;
  onToggleShared: () => void;
}

function motionMode(): string {
  return document.documentElement.dataset.motion ?? "full";
}

function FilterCheckbox({
  checked,
  label,
  onChange
}: {
  checked: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      className="flex items-center gap-3 rounded-2xl px-3 py-2 text-sm hover:bg-background transition-colors cursor-pointer"
    >
      <span
        className={`flex h-5 w-5 flex-none items-center justify-center rounded-md border ${
          checked
            ? "border-accent bg-accent text-accent-foreground"
            : "border-muted bg-transparent text-transparent"
        } transition-colors`}
      >
        <Check className="h-3 w-3" />
      </span>
      <span className="text-foreground">{label}</span>
    </button>
  );
}

export function ProjectFilterPanel({
  isOpen,
  onClose,
  projectLabels,
  enabledProjects,
  onToggleProject,
  hasLocalIssues,
  showLocal,
  showShared,
  onToggleLocal,
  onToggleShared
}: ProjectFilterPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backdropRef = useRef<HTMLDivElement | null>(null);
  const [isInteractive, setIsInteractive] = useState(false);

  useEffect(() => {
    const panel = panelRef.current;
    const backdrop = backdropRef.current;
    if (!panel || !backdrop) {
      return;
    }

    const currentMotion = motionMode();
    const duration = currentMotion === "reduced" ? 0.12 : 0.24;

    if (isOpen) {
      setIsInteractive(true);
      if (currentMotion === "off") {
        gsap.set(panel, { x: 0, opacity: 1 });
        gsap.set(backdrop, { opacity: 0.9 });
        return;
      }
      gsap.to(panel, { x: 0, opacity: 1, duration, ease: "power3.out" });
      gsap.to(backdrop, { opacity: 0.9, duration, ease: "power2.out" });
      return;
    }

    if (currentMotion === "off") {
      gsap.set(panel, { x: "120%", opacity: 0 });
      gsap.set(backdrop, { opacity: 0 });
      setIsInteractive(false);
      return;
    }

    gsap.to(panel, {
      x: "120%",
      opacity: 0,
      duration,
      ease: "power3.in"
    });
    gsap.to(backdrop, {
      opacity: 0,
      duration,
      ease: "power2.in",
      onComplete: () => setIsInteractive(false)
    });
  }, [isOpen]);

  return (
    <div
      className={`fixed inset-0 z-[9999] ${isInteractive ? "pointer-events-auto" : "pointer-events-none"}`}
      aria-hidden={!isOpen}
    >
      <div
        className={`absolute inset-0 z-0 bg-background opacity-0 ${isOpen ? "pointer-events-auto" : "pointer-events-none"}`}
        ref={backdropRef}
        onClick={onClose}
        data-testid="project-filter-backdrop"
      />
      <div
        ref={panelRef}
        className="absolute right-3 top-3 bottom-3 z-10 w-[min(360px,90vw)] rounded-3xl p-3 bg-card translate-x-[120%] opacity-0 pointer-events-auto flex flex-col"
        data-testid="project-filter-panel"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted">
            <FolderOpen className="h-4 w-4" />
            <span>Projects</span>
          </div>
          <button
            className="rounded-full bg-background px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8"
            onClick={onClose}
            type="button"
          >
            <span className="flex items-center gap-2">
              <X className="h-4 w-4" />
              <span>Close</span>
            </span>
          </button>
        </div>

        <div className="mt-3 flex flex-col gap-3 flex-1 min-h-0 overflow-y-auto">
          <div className="flex flex-col gap-1">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted px-3 mb-1">
              Project
            </div>
            {projectLabels.map((label) => (
              <FilterCheckbox
                key={label}
                checked={enabledProjects.has(label)}
                label={label}
                onChange={() => onToggleProject(label)}
              />
            ))}
          </div>

          <div className="flex flex-col gap-1">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted px-3 mb-1">
              Source
            </div>
            <FilterCheckbox
              checked={showShared}
              label="Project"
              onChange={onToggleShared}
            />
            <FilterCheckbox
              checked={showLocal}
              label="Local"
              onChange={onToggleLocal}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
