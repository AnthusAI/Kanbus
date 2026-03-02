import * as React from "react";
import {
  FeaturePictogram,
  type FeaturePictogramType,
} from "../../../apps/kanb.us/src/components/FeaturePictogram";
import { AnimatedPictogram } from "../../../apps/kanb.us/src/components/AnimatedPictogram";

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
}: {
  type?: PictogramType;
  style?: React.CSSProperties;
  scale?: number;
  innerPadding?: number;
  allowOverflow?: boolean;
}) {
  const homeType = HOME_TYPE_MAP[type] || HOME_TYPE_MAP.git;
  const isGitSyncHome = type === "git-sync-home";

  return (
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
            height: "100%",
            minHeight: 0,
            transform: `scale(${scale})`,
            transformOrigin: "center center",
          }}
        >
          <AnimatedPictogram
            showTitle={false}
            framed={false}
            className="w-full h-full"
            style={{
              width: "100%",
              height: "100%",
              ["--glow-center" as any]: "transparent",
              ["--glow-edge" as any]: "transparent",
            }}
          />
        </div>
      ) : (
        <FeaturePictogram
          type={homeType}
          className="w-full h-full min-h-0"
          style={{
            width: "100%",
            height: "100%",
            minHeight: 0,
            transform: `scale(${scale})`,
            transformOrigin: "center center",
            borderRadius: 0,
            // Flatten for video scenes: no glow gradients, no decorative backdrop.
            ["--glow-center" as any]: "transparent",
            ["--glow-edge" as any]: "transparent",
          }}
        />
      )}
    </div>
  );
}
