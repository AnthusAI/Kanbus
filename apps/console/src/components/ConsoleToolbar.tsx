import { useEffect, useState } from "react";
import { Filter } from "lucide-react";
import { AnimatedSelector, IssueTypeFilter, type SelectorOption } from "@kanbus/ui";
import type { PanelMode, SidebarTarget } from "../types/console";
import type { ProjectConfig } from "../types/issues";
import { SearchInput } from "./SearchInput";

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4">
      <path
        fill="currentColor"
        d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.5.5 0 0 0 .12-.63l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.35 7.35 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54c-.58.24-1.13.55-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.7 8.85a.5.5 0 0 0 .12.63l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58a.5.5 0 0 0-.12.63l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.39 1.05.7 1.63.94l.36 2.54a.5.5 0 0 0 .5.42h3.84a.5.5 0 0 0 .5-.42l.36-2.54c.58-.24 1.13-.55 1.63-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.63l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5z"
      />
    </svg>
  );
}

type ConsoleToolbarProps = {
  panelMode: PanelMode;
  panelModeOptions: SelectorOption[];
  onPanelModeChange: (value: string) => void;
  showLoadingIndicator: boolean;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onSearchClear: () => void;
  showTypeFilterToolbar: boolean;
  config: ProjectConfig | undefined;
  typeFilterValue: string | null;
  onTypeFilterChange: (value: string) => void;
  typeFilterOptions: SelectorOption[];
  filterOpen: boolean;
  settingsOpen: boolean;
  onOpenSidebar: (target: SidebarTarget) => void;
  onCloseSidebar: (target: SidebarTarget) => void;
};

export function ConsoleToolbar({
  panelMode,
  panelModeOptions,
  onPanelModeChange,
  showLoadingIndicator,
  searchQuery,
  onSearchChange,
  onSearchClear,
  showTypeFilterToolbar,
  config,
  typeFilterValue,
  onTypeFilterChange,
  typeFilterOptions,
  filterOpen,
  settingsOpen,
  onOpenSidebar,
  onCloseSidebar,
}: ConsoleToolbarProps) {
  const [loadingVisible, setLoadingVisible] = useState(false);

  useEffect(() => {
    if (showLoadingIndicator) {
      setLoadingVisible(true);
    }
  }, [showLoadingIndicator]);

  useEffect(() => {
    if (showLoadingIndicator) {
      return;
    }
    const timer = window.setTimeout(() => {
      setLoadingVisible(false);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [showLoadingIndicator]);

  const motionMode = typeof document !== "undefined" ? document.documentElement.dataset.motion : "full";
  const toggleMotionClass =
    motionMode === "off"
      ? ""
      : motionMode === "reduced"
      ? "transition-opacity duration-150"
      : "transition-opacity duration-300";

  return (
    <div className="flex items-center gap-2">
      <div className="flex-none">
        <AnimatedSelector
          name="panel-mode"
          value={panelMode}
          onChange={onPanelModeChange}
          options={panelModeOptions}
          testIdPrefix="view-toggle"
        />
      </div>
      <div className="flex-1 min-w-0 flex justify-end overflow-hidden gap-2">
        {loadingVisible ? (
          <span
            className={`loading-pill loading-pill--compact ${
              showLoadingIndicator ? "" : "loading-pill--hide"
            }`}
            onTransitionEnd={(event) => {
              if (event.target !== event.currentTarget) {
                return;
              }
              if (event.propertyName !== "opacity") {
                return;
              }
              if (!showLoadingIndicator) {
                setLoadingVisible(false);
              }
            }}
          >
            <span className="loading-spinner" aria-hidden="true" />
            Loading
          </span>
        ) : null}
        <SearchInput
          value={searchQuery}
          onChange={onSearchChange}
          onClear={onSearchClear}
          placeholder="Search issues..."
        />
        {showTypeFilterToolbar && panelMode !== "now" ? (
          <IssueTypeFilter
            config={config ?? {}}
            name="view"
            value={typeFilterValue}
            onChange={onTypeFilterChange}
            viewOptions={typeFilterOptions}
          />
        ) : null}
      </div>
      <button
        className="flex-none toggle-button rounded-full bg-[var(--column)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted h-7 flex items-center justify-center gap-2"
        onClick={() => {
          if (filterOpen) {
            onCloseSidebar("filter");
          } else {
            onOpenSidebar("filter");
          }
        }}
        type="button"
        data-testid="filter-button"
      >
        <span className="toggle-row flex items-center gap-2">
          <Filter className="h-4 w-4" />
          <span className={`${toggleMotionClass} whitespace-nowrap label-text toggle-label`}>
            Filter
          </span>
        </span>
      </button>
      <button
        className="flex-none flex items-center gap-2 rounded-full bg-[var(--column)] px-2 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8"
        onClick={() => {
          if (settingsOpen) {
            onCloseSidebar("settings");
          } else {
            onOpenSidebar("settings");
          }
        }}
        type="button"
        data-testid="open-settings"
      >
        <SettingsIcon />
      </button>
    </div>
  );
}
