import * as React from "react";
import { AnimatedPictogramVideo, type PictogramType } from "./AnimatedPictogramVideo";
import { BeadsDemoVideo } from "./BeadsDemoVideo";
import { CliDemoVideo } from "./CliDemoVideo";
import { JiraSyncDemoVideo } from "./JiraSyncDemoVideo";
import { LocalTasksDemoVideo } from "./LocalTasksDemoVideo";
import { PolicyDemoVideo } from "./PolicyDemoVideo";
import { VideoFeatureFrame } from "./VideoFeatureFrame";
import { VirtualProjectsDemoVideo } from "./VirtualProjectsDemoVideo";
import { VsCodeDemoVideo } from "./VsCodeDemoVideo";

type RightPanel =
  | "pictogram"
  | "cli-demo"
  | "jira-sync-demo"
  | "local-tasks-demo"
  | "beads-demo"
  | "virtual-projects-demo"
  | "vscode-demo"
  | "policy-demo";

export type FeatureTwoColumnSceneProps = {
  headline: string;
  subhead: string;
  bodyPrimary?: string;
  bodySecondary?: string;
  leftRatio?: number;
  rightPanel: RightPanel;
  pictogramType?: PictogramType;
  pictogramScale?: number;
  pictogramInnerPadding?: number;
  showDebugGuides?: boolean;
};

const panelStyle: React.CSSProperties = {
  position: "relative",
  inset: "auto",
  width: "100%",
  height: "100%",
  padding: "0",
};

export function FeatureTwoColumnScene({
  headline,
  subhead,
  bodyPrimary,
  bodySecondary,
  leftRatio,
  rightPanel,
  pictogramType = "git",
  pictogramScale = 1.16,
  pictogramInnerPadding = 16,
  showDebugGuides = false,
}: FeatureTwoColumnSceneProps) {
  let panelNode: React.ReactNode;
  switch (rightPanel) {
    case "pictogram":
      panelNode = (
        <AnimatedPictogramVideo
          type={pictogramType}
          scale={pictogramScale}
          innerPadding={pictogramInnerPadding}
          style={{ width: "100%", height: "100%" }}
        />
      );
      break;
    case "cli-demo":
      panelNode = <CliDemoVideo style={panelStyle} />;
      break;
    case "jira-sync-demo":
      panelNode = <JiraSyncDemoVideo style={panelStyle} />;
      break;
    case "local-tasks-demo":
      panelNode = <LocalTasksDemoVideo style={panelStyle} />;
      break;
    case "beads-demo":
      panelNode = <BeadsDemoVideo style={panelStyle} />;
      break;
    case "virtual-projects-demo":
      panelNode = <VirtualProjectsDemoVideo style={panelStyle} />;
      break;
    case "vscode-demo":
      panelNode = <VsCodeDemoVideo style={panelStyle} />;
      break;
    case "policy-demo":
      panelNode = <PolicyDemoVideo style={panelStyle} />;
      break;
    default:
      panelNode = null;
      break;
  }

  return (
    <VideoFeatureFrame
      headline={headline}
      subhead={subhead}
      bodyPrimary={bodyPrimary}
      bodySecondary={bodySecondary}
      leftRatio={leftRatio}
      rightPanel={panelNode}
      showDebugGuides={showDebugGuides}
    />
  );
}
