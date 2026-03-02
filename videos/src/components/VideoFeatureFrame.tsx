import * as React from "react";

export type VideoFeatureFrameProps = {
  headline: string;
  subhead: string;
  bodyPrimary?: string;
  bodySecondary?: string;
  leftRatio?: number;
  framePadding?: string;
  rightPanel: React.ReactNode;
  allowRightOverflow?: boolean;
  showDebugGuides?: boolean;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function VideoFeatureFrame({
  headline,
  subhead,
  bodyPrimary,
  bodySecondary,
  leftRatio = 0.4,
  framePadding = "24px 28px",
  rightPanel,
  allowRightOverflow = false,
  showDebugGuides = false,
}: VideoFeatureFrameProps) {
  const resolvedLeftRatio = clamp(leftRatio, 0.2, 0.55);
  const resolvedRightRatio = 1 - resolvedLeftRatio;
  const debugBorder = showDebugGuides ? "2px dashed rgba(125, 211, 252, 0.6)" : "none";

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: "var(--background)",
        color: "var(--text-foreground)",
        display: "flex",
        alignItems: "stretch",
        justifyContent: "center",
        padding: framePadding,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          display: "flex",
          gap: "16px",
          padding: "4px",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            flex: `${resolvedLeftRatio} ${resolvedLeftRatio} 0`,
            minWidth: 0,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: "8px",
            paddingTop: "4px",
            paddingBottom: "4px",
            position: "relative",
            zIndex: 2,
            outline: debugBorder,
            outlineOffset: "-2px",
          }}
        >
          <h1
            style={{
              margin: 0,
              fontFamily: '"Space Grotesk", "Inter", "SF Pro Text", "Helvetica Neue", Arial, sans-serif',
              fontSize: "44px",
              lineHeight: 1.08,
              letterSpacing: "-0.02em",
              fontWeight: 650,
              color: "var(--text-foreground)",
            }}
          >
            {headline}
          </h1>
          <p
            style={{
              margin: 0,
              fontFamily: '"IBM Plex Sans", "Inter", "SF Pro Text", "Helvetica Neue", Arial, sans-serif',
              fontSize: "22px",
              lineHeight: 1.2,
              fontWeight: 500,
              color: "var(--text-selected)",
            }}
          >
            {subhead}
          </p>
        </div>

        <div
          style={{
            flex: `${resolvedRightRatio} ${resolvedRightRatio} 0`,
            minWidth: 0,
            minHeight: 0,
            overflow: allowRightOverflow ? "visible" : "hidden",
            padding: 0,
            boxSizing: "border-box",
            display: "flex",
            alignItems: "stretch",
            justifyContent: "stretch",
            position: "relative",
            zIndex: 1,
            outline: debugBorder,
            outlineOffset: "-2px",
          }}
        >
          <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>{rightPanel}</div>
        </div>
      </div>
    </div>
  );
}
