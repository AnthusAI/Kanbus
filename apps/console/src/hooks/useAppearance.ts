import { useEffect, useState } from "react";

export type Theme = "neutral" | "cool" | "warm";
export type Mode = "light" | "dark" | "system";
export type Font = "sans" | "serif" | "mono";
export type Motion = "full" | "reduced" | "off" | "debug";

interface AppearanceState {
  theme: Theme;
  mode: Mode;
  font: Font;
  motion: Motion;
}

const STORAGE_KEY = "kanbus.console.appearance";

function getSystemReduceMotion(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function getSystemMode(): Mode {
  return "system";
}

export function useAppearance() {
  const [appearance, setAppearance] = useState<AppearanceState>(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    const debugSlowMotion =
      typeof window !== "undefined"
        ? window.localStorage.getItem("kanbus.console.debugSlowMotion") === "true"
        : false;
    const fallbackMotion: Motion = getSystemReduceMotion() ? "reduced" : "full";
    const defaultMotion: Motion = debugSlowMotion ? "debug" : fallbackMotion;
    const resolveMotion = (value?: string): Motion | null => {
      if (value === "full" || value === "reduced" || value === "off" || value === "debug") {
        return value;
      }
      return null;
    };
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Partial<AppearanceState>;
        return {
          theme: parsed.theme ?? "neutral",
          mode: parsed.mode ?? getSystemMode(),
          font: parsed.font ?? "sans",
          motion: resolveMotion(parsed.motion) ?? defaultMotion
        };
      } catch {
        return {
          theme: "neutral",
          mode: getSystemMode(),
          font: "sans",
          motion: defaultMotion
        };
      }
    }
    return {
      theme: "neutral",
      mode: getSystemMode(),
      font: "sans",
      motion: defaultMotion
    };
  });

  const updateAppearance = (updates: Partial<AppearanceState>) => {
    setAppearance((prev) => {
      const next = { ...prev, ...updates };
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      }
      return next;
    });
  };

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("theme-neutral", "theme-cool", "theme-warm");
    root.classList.add(`theme-${appearance.theme}`);

    root.classList.remove("light", "dark");
    if (appearance.mode === "system") {
      const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.classList.add(systemDark ? "dark" : "light");
    } else {
      root.classList.add(appearance.mode);
    }

    root.dataset.font = appearance.font;
    root.dataset.motion = appearance.motion;
  }, [appearance.theme, appearance.mode, appearance.font, appearance.motion]);

  useEffect(() => {
    if (appearance.mode !== "system") {
      return;
    }
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => {
      const root = document.documentElement;
      root.classList.remove("light", "dark");
      root.classList.add(mediaQuery.matches ? "dark" : "light");
    };
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [appearance.mode]);

  return {
    appearance,
    setTheme: (theme: Theme) => updateAppearance({ theme }),
    setMode: (mode: Mode) => updateAppearance({ mode }),
    setFont: (font: Font) => updateAppearance({ font }),
    setMotion: (motion: Motion) => updateAppearance({ motion })
  };
}
