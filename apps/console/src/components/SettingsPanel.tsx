import React from "react";
import {
  Check,
  Monitor,
  Moon,
  Sun,
  Settings,
  Type,
} from "lucide-react";
import { useAppearance } from "../hooks/useAppearance";
import { AnimatedSelector } from "@kanbus/ui";
import { RightSidebar } from "./RightSidebar";

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  showTypeFilterToolbar: boolean;
  showInitiativesInTypeFilter: boolean;
  onToggleShowTypeFilterToolbar: () => void;
  onToggleShowInitiativesInTypeFilter: () => void;
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
  onClose,
  showTypeFilterToolbar,
  showInitiativesInTypeFilter,
  onToggleShowTypeFilterToolbar,
  onToggleShowInitiativesInTypeFilter
}: SettingsPanelProps) {
  const { appearance, setMode, setTheme, setFont, setMotion } = useAppearance();
  return (
    <RightSidebar
      isOpen={isOpen}
      onClose={onClose}
      title="Settings"
      icon={<Settings className="h-4 w-4" />}
      testId="settings-panel"
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
        <div className="grid grid-cols-3 gap-2">
          {[
            {
              id: "neutral",
              label: "Neutral",
              swatches: ["swatch-neutral-1", "swatch-neutral-2", "swatch-neutral-3"]
            },
            {
              id: "cool",
              label: "Cool",
              swatches: ["swatch-cool-1", "swatch-cool-2", "swatch-cool-3"]
            },
            {
              id: "warm",
              label: "Warm",
              swatches: ["swatch-warm-1", "swatch-warm-2", "swatch-warm-3"]
            }
          ].map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setTheme(option.id as any)}
              data-selector="theme"
              data-option={option.id}
              className={`rounded-full h-10 px-3 flex flex-col items-center justify-center gap-1 text-[10px] font-semibold uppercase tracking-[0.2em] ${
                appearance.theme === option.id ? "text-foreground bg-card-muted" : "text-muted bg-card"
              }`}
            >
              <span className="selector-swatches">
                {option.swatches.map((color) => (
                  <span
                    key={color}
                    className={`theme-swatch ${color}`}
                  />
                ))}
              </span>
              <span className="selector-label">{option.label}</span>
            </button>
          ))}
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
            { id: "off", label: "Off" }
          ]}
        />
      </div>

      <div className="grid gap-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
          Typeface
        </div>
        <AnimatedSelector
          name="font"
          value={appearance.font}
          onChange={(value) => setFont(value as any)}
          className="w-full"
          options={[
            {
              id: "sans",
              label: "Sans",
              content: (
                <span className="selector-option">
                  <Type className="h-4 w-4" />
                  <span className="selector-label font-sans">Sans</span>
                </span>
              )
            },
            {
              id: "serif",
              label: "Serif",
              content: (
                <span className="selector-option">
                  <Type className="h-4 w-4" />
                  <span className="selector-label font-[var(--font-serif)]">
                    Serif
                  </span>
                </span>
              )
            },
            {
              id: "mono",
              label: "Mono",
              content: (
                <span className="selector-option">
                  <Type className="h-4 w-4" />
                  <span className="selector-label font-[var(--font-mono)]">
                    Mono
                  </span>
                </span>
              )
            }
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
