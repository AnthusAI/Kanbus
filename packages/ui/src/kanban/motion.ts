import type { CSSProperties } from "react";

export type KanbanMotionMode = "css" | "frame" | "static";

export interface KanbanMotionConfig {
  mode: KanbanMotionMode;
  frame?: number;
  fps?: number;
  staggerFrames?: number;
  durationFrames?: number;
}

const DEFAULT_STAGGER = 4;
const DEFAULT_DURATION = 18;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function easeOutCubic(value: number): number {
  return 1 - Math.pow(1 - value, 3);
}

export function normalizeMotionConfig(
  config?: KanbanMotionConfig
): KanbanMotionConfig {
  if (!config) {
    return { mode: "css" };
  }
  return config;
}

export function getIssueMotionStyle(
  config: KanbanMotionConfig | undefined,
  index: number
): CSSProperties | undefined {
  if (!config || config.mode !== "frame") {
    return undefined;
  }

  const frame = config.frame ?? 0;
  const stagger = config.staggerFrames ?? DEFAULT_STAGGER;
  const duration = config.durationFrames ?? DEFAULT_DURATION;
  const start = index * stagger;
  const progress = clamp((frame - start) / duration, 0, 1);
  const eased = easeOutCubic(progress);
  const translateY = (1 - eased) * 14;
  const scale = 0.96 + 0.04 * eased;

  return {
    opacity: eased,
    transform: `translateY(${translateY}px) scale(${scale})`
  };
}
