import React from "react";
import { useCurrentFrame, useVideoConfig } from "../remotion-shim";
import { AnimatedPictogramVideo, type PictogramType } from "./AnimatedPictogramVideo";

type FeatureSpotlight = {
  title: string;
  subtitle: string;
  type: PictogramType;
};

const FEATURE_SPOTLIGHTS: FeatureSpotlight[] = [
  {
    title: "Agent-Ready CLI",
    subtitle: "Create, update, and track issues from terminal-native workflows.",
    type: "cli",
  },
  {
    title: "Kanban Board",
    subtitle: "A visual board that stays in sync with repository state.",
    type: "git",
  },
  {
    title: "Jira Sync",
    subtitle: "Pull Jira tasks into your repo so agents always have context.",
    type: "jira",
  },
  {
    title: "Local Tasks",
    subtitle: "Keep private WIP local and promote it when ready.",
    type: "local",
  },
  {
    title: "Virtual Projects",
    subtitle: "Aggregate cross-repository work into one view.",
    type: "virtual",
  },
  {
    title: "Beads Mode",
    subtitle: "Use existing Beads projects without migration overhead.",
    type: "beads",
  },
  {
    title: "VS Code Plugin",
    subtitle: "Manage your board directly inside the editor.",
    type: "vscode",
  },
  {
    title: "Integrated Wiki",
    subtitle: "Generate live planning docs from issue data.",
    type: "wiki",
  },
  {
    title: "Policy as Code",
    subtitle: "Enforce workflow standards with executable policies.",
    type: "policy",
  },
];

const SECONDS_PER_FEATURE = 3;

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const featureIndex = Math.min(
    FEATURE_SPOTLIGHTS.length - 1,
    Math.floor(frame / (fps * SECONDS_PER_FEATURE)),
  );
  const active = FEATURE_SPOTLIGHTS[featureIndex];

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "20px",
        padding: "72px",
        backgroundColor: "#0f1115",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <div style={{ fontSize: "22px", color: "#7dd3fc", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          Kanbus Feature Tour
        </div>
        <div style={{ fontSize: "56px", fontWeight: 800, color: "#e7e9ee", lineHeight: 1.1 }}>
          {active.title}
        </div>
        <div style={{ fontSize: "24px", color: "#9ca3af", maxWidth: "1160px" }}>
          {active.subtitle}
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <AnimatedPictogramVideo
          type={active.type}
          style={{
            width: "100%",
            height: "100%",
            minHeight: "420px",
            padding: "24px",
            borderRadius: "18px",
            backgroundColor: "#14171d",
          }}
        />
      </div>

      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
        {FEATURE_SPOTLIGHTS.map((feature, idx) => (
          <div
            key={feature.title}
            style={{
              padding: "8px 14px",
              borderRadius: "999px",
              fontSize: "16px",
              fontWeight: 600,
              color: idx === featureIndex ? "#0f1115" : "#e7e9ee",
              backgroundColor: idx === featureIndex ? "#7dd3fc" : "#1f2430",
              border: idx === featureIndex ? "1px solid #7dd3fc" : "1px solid #2c3443",
            }}
          >
            {feature.title}
          </div>
        ))}
      </div>
    </div>
  );
};
