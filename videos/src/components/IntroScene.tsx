import * as React from "react";
import { useCurrentFrame, useVideoConfig } from "../remotion-shim";
import { AnimatedPictogramVideo, type PictogramType } from "./AnimatedPictogramVideo";
import { VideoFeatureFrame } from "./VideoFeatureFrame";

type IntroSceneMode = "kanban-home" | "git-sync-home" | "feature" | "cta";

type IntroSceneProps = {
  mode?: IntroSceneMode;
  feature?: PictogramType;
  showDebugGuides?: boolean;
};

type FeatureSpotlight = {
  headline: string;
  subhead: string;
  bodyPrimary: string;
  type: PictogramType;
};

const FEATURE_SPOTLIGHTS: FeatureSpotlight[] = [
  {
    headline: "Agent-Ready CLI",
    subhead: "Run Kanbus in scripts and agent loops.",
    bodyPrimary:
      "Create, update, and move work from your terminal without leaving repository-native workflows.",
    type: "cli",
  },
  {
    headline: "Jira Synchronization",
    subhead: "Bring Jira context into the repo.",
    bodyPrimary:
      "Sync existing Jira projects into local files so agents and humans work from the same source of truth.",
    type: "jira",
  },
  {
    headline: "Local Tasks",
    subhead: "Draft privately, promote when ready.",
    bodyPrimary:
      "Keep work-in-progress local, then publish tasks to the shared board when they are ready for team visibility.",
    type: "local",
  },
  {
    headline: "Virtual Projects",
    subhead: "Track multiple repos in one board.",
    bodyPrimary:
      "Aggregate cross-repository execution into a single view for planning and delivery coordination.",
    type: "virtual",
  },
  {
    headline: "Beads Compatibility",
    subhead: "Adopt Kanbus without a migration freeze.",
    bodyPrimary:
      "Open existing Beads data immediately and evolve your process incrementally while teams keep shipping.",
    type: "beads",
  },
  {
    headline: "VS Code Plugin",
    subhead: "Manage workflow inside the editor.",
    bodyPrimary:
      "Inspect and update board state without context switching away from the files you are editing.",
    type: "vscode",
  },
  {
    headline: "Integrated Wiki",
    subhead: "Planning docs backed by live tasks.",
    bodyPrimary:
      "Render current issue lists inside docs so plans, status updates, and execution context stay synchronized.",
    type: "wiki",
  },
  {
    headline: "Policy as Code",
    subhead: "Enforce rules for humans and agents.",
    bodyPrimary:
      "Define standards once and apply them consistently across CLI usage, automation, and collaborative workflows.",
    type: "policy",
  },
];


function StaticIntroFrame({
  headline,
  subhead,
  bodyPrimary,
  type,
  scale,
  leftRatio = 0.4,
  framePadding,
  allowRightOverflow = false,
  allowPictogramOverflow = false,
  showDebugGuides,
  frame,
  fps,
}: {
  headline: string;
  subhead: string;
  bodyPrimary: string;
  type: PictogramType;
  scale: number;
  leftRatio?: number;
  framePadding?: string;
  allowRightOverflow?: boolean;
  allowPictogramOverflow?: boolean;
  showDebugGuides: boolean;
  frame: number;
  fps: number;
}) {
  return (
    <VideoFeatureFrame
      headline={headline}
      subhead={subhead}
      bodyPrimary={bodyPrimary}
      leftRatio={leftRatio}
      framePadding={framePadding}
      allowRightOverflow={allowRightOverflow}
      showDebugGuides={showDebugGuides}
      rightPanel={
        <AnimatedPictogramVideo
          type={type}
          scale={scale}
          innerPadding={0}
          allowOverflow={allowPictogramOverflow}
          frame={frame}
          fps={fps}
        />
      }
    />
  );
}

function FeatureSlide({
  feature,
  translateX,
  showDebugGuides,
  frame,
  fps,
}: {
  feature: FeatureSpotlight;
  translateX: number;
  showDebugGuides: boolean;
  frame: number;
  fps: number;
}) {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        transform: `translateX(${translateX}%)`,
      }}
    >
      <VideoFeatureFrame
        headline={feature.headline}
        subhead={feature.subhead}
        bodyPrimary={feature.bodyPrimary}
        leftRatio={0.4}
        showDebugGuides={showDebugGuides}
        rightPanel={
          <AnimatedPictogramVideo
            type={feature.type}
            scale={1.17}
            innerPadding={0}
            frame={frame}
            fps={fps}
          />
        }
      />
    </div>
  );
}

export const IntroScene: React.FC<IntroSceneProps> = ({
  mode = "feature",
  feature,
  showDebugGuides = false,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (mode === "kanban-home") {
    return (
      <StaticIntroFrame
        headline="Repository Kanban"
        subhead="Accessible board + CLI from plain files."
        bodyPrimary="Kanbus gives your team and agents one shared workflow: a live board backed by repository-native issue files."
        type="kanban-home"
        scale={1.017}
        leftRatio={0.24}
        allowRightOverflow={true}
        allowPictogramOverflow={true}
        showDebugGuides={showDebugGuides}
        frame={frame}
        fps={fps}
      />
    );
  }

  if (mode === "git-sync-home") {
    return (
      <StaticIntroFrame
        headline="Git Synchronization"
        subhead="Use Git as the bus for kanban boards."
        bodyPrimary="Board updates become normal file changes, so review, history, branching, and collaboration stay native to your existing engineering workflow."
        type="git-sync-home"
        scale={1.08}
        leftRatio={0.34}
        framePadding="0px 28px"
        allowRightOverflow={true}
        allowPictogramOverflow={true}
        showDebugGuides={showDebugGuides}
        frame={frame}
        fps={fps}
      />
    );
  }

  if (mode === "cta") {
    return (
      <StaticIntroFrame
        headline="Get started with Kanbus"
        subhead="Install quickly and run the workflow today."
        bodyPrimary="Visit kanb.us for docs, setup guides, and the complete feature walkthrough."
        type="cli"
        scale={1.098}
        showDebugGuides={showDebugGuides}
        frame={frame}
        fps={fps}
      />
    );
  }

  const spotlight = FEATURE_SPOTLIGHTS.find((f) => f.type === feature) ?? FEATURE_SPOTLIGHTS[0];

  return (
    <FeatureSlide
      feature={spotlight}
      translateX={0}
      showDebugGuides={showDebugGuides}
      frame={frame}
      fps={fps}
    />
  );
};
