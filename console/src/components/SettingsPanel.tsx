import React, { useEffect, useRef, useState } from "react";
import {
  Monitor,
  Moon,
  Sun,
  Settings,
  Type
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
      className="fixed inset-0"
      style={{
        pointerEvents: isInteractive ? "auto" : "none",
        zIndex: 9999
      }}
      aria-hidden={!isOpen}
    >
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: "var(--background)",
          opacity: 0,
          pointerEvents: isOpen ? "auto" : "none",
          zIndex: 0
        }}
        ref={backdropRef}
        onClick={onClose}
        data-testid="settings-backdrop"
      />
      <div
        ref={panelRef}
        className="absolute right-3 top-3 bottom-3 w-[min(360px,90vw)] rounded-3xl p-3"
        data-testid="settings-panel"
        style={{
          transform: "translateX(120%)",
          backgroundColor: "var(--card)",
          pointerEvents: "auto",
          zIndex: 1
        }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted">
            <Settings className="h-3 w-3" />
            <span>Settings</span>
          </div>
          <button
            className="rounded-full bg-card px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        <div className="mt-3 grid gap-3">
          <div className="grid gap-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
              Mode
            </div>
          <AnimatedSelector
            name="mode"
            value={appearance.mode}
            onChange={(value) => setMode(value as any)}
            className="w-full flex-wrap"
            options={[
              {
                id: "light",
                label: "Light",
                content: (
                  <span className="selector-option">
                    <Sun className="h-3 w-3" />
                    <span className="selector-label">Light</span>
                  </span>
                )
              },
              {
                id: "dark",
                label: "Dark",
                content: (
                  <span className="selector-option">
                    <Moon className="h-3 w-3" />
                    <span className="selector-label">Dark</span>
                  </span>
                )
              },
              {
                id: "system",
                label: "System",
                content: (
                  <span className="selector-option">
                    <Monitor className="h-3 w-3" />
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
          <AnimatedSelector
            name="theme"
            value={appearance.theme}
            onChange={(value) => setTheme(value as any)}
            className="w-full flex-wrap"
            options={[
              {
                id: "neutral",
                label: "Neutral",
                content: (
                  <span className="selector-option">
                    <span className="selector-swatches">
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--gray-3)" }} />
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--gray-6)" }} />
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--gray-9)" }} />
                    </span>
                    <span className="selector-label">Neutral</span>
                  </span>
                )
              },
              {
                id: "cool",
                label: "Cool",
                content: (
                  <span className="selector-option">
                    <span className="selector-swatches">
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--blue-3)" }} />
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--blue-6)" }} />
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--blue-9)" }} />
                    </span>
                    <span className="selector-label">Cool</span>
                  </span>
                )
              },
              {
                id: "warm",
                label: "Warm",
                content: (
                  <span className="selector-option">
                    <span className="selector-swatches">
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--sand-3)" }} />
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--sand-6)" }} />
                      <span className="h-2 w-2 rounded-full" style={{ background: "var(--sand-9)" }} />
                    </span>
                    <span className="selector-label">Warm</span>
                  </span>
                )
              }
            ]}
          />
        </div>

          <div className="grid gap-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
              Motion
            </div>
          <AnimatedSelector
            name="motion"
            value={appearance.motion}
            onChange={(value) => setMotion(value as any)}
            className="w-full flex-wrap"
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
            className="w-full flex-wrap"
            options={[
              {
                id: "sans",
                label: "Sans",
                content: (
                  <span className="selector-option">
                    <Type className="h-3 w-3" />
                    <span className="selector-label font-sans">Sans</span>
                  </span>
                )
              },
              {
                id: "serif",
                label: "Serif",
                content: (
                  <span className="selector-option">
                    <Type className="h-3 w-3" />
                    <span className="selector-label" style={{ fontFamily: "var(--font-serif)" }}>
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
                    <Type className="h-3 w-3" />
                    <span className="selector-label" style={{ fontFamily: "var(--font-mono)" }}>
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
