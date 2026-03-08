import * as React from "react";
import {
  FeaturePictogram,
  type FeaturePictogramType,
} from "../../../apps/kanb.us/src/components/FeaturePictogram";
import { AnimatedPictogram } from "../../../apps/kanb.us/src/components/AnimatedPictogram";
import { VideoFeatureFrame } from "./VideoFeatureFrame";

export type PictogramType =
  | "git"
  | "git-sync"
  | "kanban-home"
  | "git-sync-home"
  | "cli"
  | "jira"
  | "local"
  | "beads"
  | "virtual"
  | "vscode"
  | "wiki"
  | "policy";

const HOME_TYPE_MAP: Record<PictogramType, FeaturePictogramType> = {
  git: "kanban-board",
  "git-sync": "jira-sync",
  "kanban-home": "kanban-board",
  "git-sync-home": "jira-sync",
  cli: "core-management",
  jira: "jira-sync",
  local: "local-tasks",
  beads: "beads-compatibility",
  virtual: "virtual-projects",
  vscode: "vscode-plugin",
  wiki: "integrated-wiki",
  policy: "policy-as-code",
};

export function AnimatedPictogramVideo({
  type = "git",
  style,
  scale = 1,
  innerPadding = 0,
  allowOverflow = false,
  headline,
  subhead,
  frame,
  fps,
}: {
  type?: PictogramType;
  style?: React.CSSProperties;
  scale?: number;
  innerPadding?: number;
  allowOverflow?: boolean;
  headline?: string;
  subhead?: string;
  frame?: number;
  fps?: number;
}) {
  const homeType = HOME_TYPE_MAP[type] || HOME_TYPE_MAP.git;
  const isGitSyncHome = type === "git-sync-home";

  const pictogram = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        padding: `${innerPadding}px`,
        overflow: allowOverflow ? "visible" : "hidden",
        minHeight: 0,
        background: "transparent",
        ...(style || { width: "100%", height: "100%" }),
      }}
    >
      {isGitSyncHome ? (
        <div
          style={{
            width: "100%",
            transform: `scale(${scale})`,
            transformOrigin: "60% center",
          }}
        >
          <AnimatedPictogram
            showTitle={false}
            framed={false}
            frame={frame}
            fps={fps}
            className="w-full"
            style={{
              ["--glow-center" as any]: "transparent",
              ["--glow-edge" as any]: "transparent",
            }}
          />
        </div>
      ) : (
        <FeaturePictogram
          type={homeType}
          frame={frame}
          fps={fps}
          allowOverflow={scale !== 1}
          className="w-full min-h-0"
          style={{
            transform: `scale(${scale})`,
            transformOrigin: "60% center",
            borderRadius: 0,
            // Flatten for video scenes: no glow gradients, no decorative backdrop.
            ["--glow-center" as any]: "transparent",
            ["--glow-edge" as any]: "transparent",
          }}
        />
      )}
    </div>
  );

  if (headline && subhead) {
    return (
      <VideoFeatureFrame
        headline={headline}
        subhead={subhead}
        rightPanel={pictogram}
      />
    );
  }

  return pictogram;
}
