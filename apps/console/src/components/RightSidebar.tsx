import React from "react";
import { X } from "lucide-react";

interface RightSidebarProps {
  isOpen: boolean;
  isVisible?: boolean;
  animate?: boolean;
  title: string;
  icon?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  testId?: string;
  onTransitionEnd?: (event: React.TransitionEvent<HTMLDivElement>) => void;
}

export function RightSidebar({
  isOpen,
  isVisible = false,
  animate = false,
  title,
  icon,
  onClose,
  children,
  testId,
  onTransitionEnd
}: RightSidebarProps) {
  return (
    <div
      className={`sidebar-column${isVisible ? " sidebar-column-visible" : ""}${
        animate ? " sidebar-column-animate" : ""
      }${isOpen ? " sidebar-column-open" : ""}`}
      aria-hidden={!isOpen}
      data-testid={testId}
      onTransitionEnd={onTransitionEnd}
    >
      <div className="flex h-full flex-col p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted">
            {icon}
            <span>{title}</span>
          </div>
          <button
            className="rounded-full bg-background px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8"
            onClick={onClose}
            type="button"
            data-testid={testId ? `${testId}-close` : undefined}
          >
            <span className="flex items-center gap-2">
              <X className="h-4 w-4" />
              <span>Close</span>
            </span>
          </button>
        </div>
        <div className="mt-3 flex flex-col gap-3 flex-1 min-h-0 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
