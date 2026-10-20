import { useEffect, useState } from "react";
import {
  DEFAULT_KANBUS_THEME,
  isKanbusThemeId,
  type KanbusThemeId
} from "@kanbus/ui";

export type Theme = KanbusThemeId;
export type Mode = "light" | "dark" | "system";
export type Motion = "full" | "reduced" | "off" | "debug";

interface AppearanceState {
  theme: Theme;
  mode: Mode;
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
          theme: isKanbusThemeId(parsed.theme) ? parsed.theme : DEFAULT_KANBUS_THEME,
          mode: parsed.mode ?? getSystemMode(),
          motion: resolveMotion(parsed.motion) ?? defaultMotion
        };
      } catch {
        return {
          theme: DEFAULT_KANBUS_THEME,
          mode: getSystemMode(),
          motion: defaultMotion
        };
      }
    }
    return {
      theme: DEFAULT_KANBUS_THEME,
      mode: getSystemMode(),
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
    root.dataset.kanbusTheme = appearance.theme;
    root.dataset.motion = appearance.motion;

    const applyMode = (dark: boolean) => {
      root.classList.remove("light", "dark");
      root.classList.add(dark ? "dark" : "light");
      root.dataset.colorMode = dark ? "dark" : "light";
    };
    if (appearance.mode !== "system") {
      applyMode(appearance.mode === "dark");
      return;
    }
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    applyMode(mediaQuery.matches);
    const handleChange = () => applyMode(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [appearance.theme, appearance.mode, appearance.motion]);

  return {
    appearance,
    setTheme: (theme: Theme) => updateAppearance({ theme }),
    setMode: (mode: Mode) => updateAppearance({ mode }),
    setMotion: (motion: Motion) => updateAppearance({ motion })
  };
}
