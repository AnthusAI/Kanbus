import React from "react";
import {
  Check,
  Monitor,
  Moon,
  Sun,
  Settings,
} from "lucide-react";
import { useAppearance } from "../hooks/useAppearance";
import { AnimatedSelector, KANBUS_THEMES } from "@kanbus/ui";
import { RightSidebar } from "./RightSidebar";

interface SettingsPanelProps {
  isOpen: boolean;
  isVisible?: boolean;
  animate?: boolean;
  onClose: () => void;
  showTypeFilterToolbar: boolean;
  showInitiativesInTypeFilter: boolean;
  onToggleShowTypeFilterToolbar: () => void;
  onToggleShowInitiativesInTypeFilter: () => void;
  onTransitionEnd?: (event: React.TransitionEvent<HTMLDivElement>) => void;
}

function SettingsToggle({
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

export function SettingsPanel({
  isOpen,
  isVisible = false,
  animate = false,
  onClose,
  showTypeFilterToolbar,
  showInitiativesInTypeFilter,
  onToggleShowTypeFilterToolbar,
  onToggleShowInitiativesInTypeFilter,
  onTransitionEnd
}: SettingsPanelProps) {
  const { appearance, setMode, setTheme, setMotion } = useAppearance();
  const resolvedMode =
    appearance.mode === "system"
      ? typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : appearance.mode;
  return (
    <RightSidebar
      isOpen={isOpen}
      isVisible={isVisible}
      animate={animate}
      onClose={onClose}
      title="Settings"
      icon={<Settings className="h-4 w-4" />}
      testId="settings-panel"
      onTransitionEnd={onTransitionEnd}
    >
      <div className="grid gap-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
          Mode
        </div>
        <AnimatedSelector
          name="mode"
          value={appearance.mode}
          onChange={(value) => setMode(value as any)}
          className="w-full"
          options={[
            {
              id: "light",
              label: "Light",
              content: (
                <span className="selector-option">
                  <Sun className="h-4 w-4" />
                  <span className="selector-label">Light</span>
                </span>
              )
            },
            {
              id: "dark",
              label: "Dark",
              content: (
                <span className="selector-option">
                  <Moon className="h-4 w-4" />
                  <span className="selector-label">Dark</span>
                </span>
              )
            },
            {
              id: "system",
              label: "System",
              content: (
                <span className="selector-option">
                  <Monitor className="h-4 w-4" />
                  <span className="selector-label">System</span>
                </span>
              )
            }
          ]}
        />
      </div>

      <div className="grid gap-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
          Theme
        </div>
        <div className="grid gap-2" role="radiogroup" aria-label="Theme">
          {KANBUS_THEMES.map((option) => {
            const selected = appearance.theme === option.id;
            return (
              <button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setTheme(option.id)}
                data-selector="theme"
                data-option={option.id}
                title={option.pairing}
                className={`flex items-center gap-3 rounded-2xl border px-3 py-2 text-left ${
                  selected ? "border-[var(--text-foreground)] bg-card-muted" : "border-transparent bg-card"
                }`}
              >
                <span
                  className="theme-swatch"
                  data-kanbus-theme={option.id}
                  data-color-mode={resolvedMode}
                  aria-hidden="true"
                >
                  <span className="theme-swatch-paper" />
                  <span className="theme-swatch-accent" />
                </span>
                <span className="grid min-w-0 gap-0.5">
                  <span className="text-sm font-semibold text-foreground">{option.name}</span>
                  <span className="text-xs text-muted">{option.titleFace} titles</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
          Motion
        </div>
        <AnimatedSelector
          name="motion"
          value={appearance.motion}
          onChange={(value) => setMotion(value as any)}
          className="w-full"
          options={[
            { id: "full", label: "Full" },
            { id: "reduced", label: "Reduced" },
            { id: "off", label: "Off" },
            { id: "debug", label: "Debug" }
          ]}
        />
      </div>

      <div className="grid gap-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
          Type Filter
        </div>
        <SettingsToggle
          checked={showTypeFilterToolbar}
          label="Show type filter in toolbar"
          onChange={onToggleShowTypeFilterToolbar}
        />
        <SettingsToggle
          checked={showInitiativesInTypeFilter}
          label="Show Initiatives in type filter"
          onChange={onToggleShowInitiativesInTypeFilter}
        />
      </div>

    </RightSidebar>
  );
}
