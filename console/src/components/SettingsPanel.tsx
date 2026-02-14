import React, { useEffect, useRef, useState } from "react";
import {
  Monitor,
  Moon,
  Sun,
  Settings,
  Type,
  X
} from "lucide-react";
import gsap from "gsap";
import { useAppearance } from "../hooks/useAppearance";
import { AnimatedSelector } from "./ui/animated-selector";

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

function motionMode(): string {
  return document.documentElement.dataset.motion ?? "full";
}

export function SettingsPanel({ isOpen, onClose }: SettingsPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backdropRef = useRef<HTMLDivElement | null>(null);
  const [isInteractive, setIsInteractive] = useState(false);
  const { appearance, setMode, setTheme, setFont, setMotion } = useAppearance();

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
        data-testid="settings-backdrop"
      />
      <div
        ref={panelRef}
        className="absolute right-3 top-3 bottom-3 z-10 w-[min(360px,90vw)] rounded-3xl p-3 bg-card translate-x-[120%] opacity-0 pointer-events-auto flex flex-col"
        data-testid="settings-panel"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted">
            <Settings className="h-4 w-4" />
            <span>Settings</span>
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
        </div>
      </div>
    </div>
  );
}
