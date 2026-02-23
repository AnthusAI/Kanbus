import React from "react";
import { Check, Filter, Focus } from "lucide-react";
import { AnimatedSelector, type SelectorOption } from "@kanbus/ui";
import { RightSidebar } from "./RightSidebar";

interface FilterSidebarProps {
  isOpen: boolean;
  isVisible?: boolean;
  animate?: boolean;
  onClose: () => void;
  focusedIssueLabel: string | null;
  onClearFocus: () => void;
  projectLabels: string[];
  enabledProjects: ReadonlySet<string>;
  onToggleProject: (label: string) => void;
  hasVirtualProjects: boolean;
  hasLocalIssues: boolean;
  showLocal: boolean;
  showShared: boolean;
  onToggleLocal: () => void;
  onToggleShared: () => void;
  typeOptions: SelectorOption[];
  typeValue: string | null;
  onTypeChange: (value: string) => void;
  onTransitionEnd?: (event: React.TransitionEvent<HTMLDivElement>) => void;
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

function FocusPill({
  label,
  onClear
}: {
  label: string;
  onClear: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClear}
      className="flex items-center justify-between gap-3 rounded-full bg-card-muted px-3 py-2 text-left hover:bg-background transition-colors"
      data-testid="filter-focus-pill"
    >
      <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
        <Focus className="h-4 w-4" />
        <span>Focused</span>
      </span>
      <span className="flex-1 text-sm text-foreground truncate">{label}</span>
      <span className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
        Clear
      </span>
    </button>
  );
}

export function FilterSidebar({
  isOpen,
  isVisible = false,
  animate = false,
  onClose,
  focusedIssueLabel,
  onClearFocus,
  projectLabels,
  enabledProjects,
  onToggleProject,
  hasVirtualProjects,
  hasLocalIssues,
  showLocal,
  showShared,
  onToggleLocal,
  onToggleShared,
  typeOptions,
  typeValue,
  onTypeChange,
  onTransitionEnd
}: FilterSidebarProps) {
  const hasProjects = projectLabels.length > 1 || hasVirtualProjects;
  const hasFocus = Boolean(focusedIssueLabel);

  return (
    <RightSidebar
      isOpen={isOpen}
      isVisible={isVisible}
      animate={animate}
      onClose={onClose}
      title="Filter"
      icon={<Filter className="h-4 w-4" />}
      testId="filter-sidebar"
      onTransitionEnd={onTransitionEnd}
    >
      {hasFocus && focusedIssueLabel ? (
        <div className="flex flex-col gap-2" data-testid="filter-focus-section">
          <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted px-3">
            Focus
          </div>
          <FocusPill label={focusedIssueLabel} onClear={onClearFocus} />
        </div>
      ) : null}

      {hasProjects ? (
        <div className="flex flex-col gap-1" data-testid="filter-projects-section">
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
      ) : null}

      <div className="flex flex-col gap-3" data-testid="filter-type-section">
        <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted px-3">
          Type
        </div>
        <AnimatedSelector
          name="type-filter"
          value={typeValue}
          onChange={onTypeChange}
          className="w-full"
          options={typeOptions}
        />
      </div>

      {hasLocalIssues ? (
        <div className="flex flex-col gap-1" data-testid="filter-source-section">
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
      ) : null}
    </RightSidebar>
  );
}
