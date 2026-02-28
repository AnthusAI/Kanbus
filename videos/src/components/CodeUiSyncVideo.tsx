import * as React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "../remotion-shim";
import { IssueCard } from "@kanbus/ui";

const boardConfig = {
  statuses: [
    { key: "backlog", name: "Backlog", category: "To do" },
    { key: "in_progress", name: "In Progress", category: "In progress" },
    { key: "closed", name: "Done", category: "Done" }
  ],
  categories: [
    { name: "To do", color: "grey" },
    { name: "In progress", color: "blue" },
    { name: "Done", color: "green" }
  ],
  priorities: {
    1: { name: "high", color: "bright_red" },
    2: { name: "medium", color: "yellow" },
    3: { name: "low", color: "blue" }
  },
  type_colors: {
    epic: "magenta",
    task: "blue",
    bug: "red",
    story: "yellow",
    chore: "green",
    "sub-task": "violet"
  }
};

const priorityLookup = {
  1: "high",
  2: "medium",
  3: "low"
};

const FILES = [
  {
    filename: "issues/PROJ-1a2b3c.json",
    issue: {
      id: "PROJ-1a2b3c",
      title: "Calibrate flux capacitor",
      type: "epic",
      status: "backlog",
      priority: 2,
      assignee: "Codex",
    }
  },
  {
    filename: "issues/PROJ-4d5e6f.json",
    issue: {
      id: "PROJ-4d5e6f",
      title: "Stabilize warp core coolant loop",
      type: "task",
      status: "in_progress",
      priority: 1,
      assignee: "Ryan",
    }
  },
  {
    filename: "issues/PROJ-7g8h9i.json",
    issue: {
      id: "PROJ-7g8h9i",
      title: "Diagnose tachyon scanner drift",
      type: "bug",
      status: "in_progress",
      priority: 1,
      assignee: "Claude",
    }
  }
];

export function CodeUiSyncVideo() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const intervalFrames = fps * 4.5;
  const activeIndex = Math.floor(frame / intervalFrames) % FILES.length;
  const transitionFrame = frame % intervalFrames;

  const transitionDuration = fps * 0.2;
  const codeOpacityIn = interpolate(transitionFrame, [0, transitionDuration], [0, 1], { extrapolateRight: "clamp" });
  const codeYIn = interpolate(transitionFrame, [0, transitionDuration], [10, 0], { extrapolateRight: "clamp" });

  const boardSpring = spring({
    frame: transitionFrame,
    fps,
    config: {
      damping: 30,
      stiffness: 300,
    }
  });

  return (
    <div style={{
      width: "100%",
      display: "flex",
      flexDirection: "row",
      gap: "32px",
      alignItems: "stretch",
      justifyContent: "center",
      position: "relative",
      padding: "32px"
    }}>
      {/* Code Window */}
      <div style={{ flex: 1, width: "100%", maxWidth: "576px" }}>
        <div style={{
          backgroundColor: "var(--card)",
          borderRadius: "12px",
          fontFamily: "monospace",
          fontSize: "14px",
          lineHeight: "2",
          overflow: "hidden",
          height: "100%",
          display: "flex",
          flexDirection: "column"
        }}>
          {/* Tab bar */}
          <div style={{
            color: "var(--text-muted)",
            display: "flex",
            alignItems: "center",
            gap: "16px",
            backgroundColor: "var(--card-muted)",
            padding: "16px",
            borderBottom: "1px solid var(--border)"
          }}>
            <div style={{ display: "flex", gap: "8px" }}>
              <span style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "rgba(239,68,68,0.5)", display: "inline-block" }} />
              <span style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "rgba(234,179,8,0.5)", display: "inline-block" }} />
              <span style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "rgba(34,197,94,0.5)", display: "inline-block" }} />
            </div>
            <div style={{ display: "flex", flex: 1, gap: "8px", overflowX: "auto" }}>
              {FILES.map((file, idx) => (
                <div
                  key={file.filename}
                  style={{
                    padding: "4px 12px",
                    borderRadius: "6px",
                    fontSize: "12px",
                    whiteSpace: "nowrap",
                    backgroundColor: activeIndex === idx ? "var(--background)" : "transparent",
                    color: activeIndex === idx ? "var(--text-foreground)" : "var(--text-muted)"
                  }}
                >
                  {file.filename.split('/')[1]}
                </div>
              ))}
            </div>
          </div>

          <div style={{ position: "relative", height: "260px", padding: "24px" }}>
            <div
              style={{
                position: "absolute",
                inset: 0,
                padding: "24px",
                overflow: "hidden",
                whiteSpace: "pre",
                color: "var(--foreground)",
                opacity: codeOpacityIn,
                transform: `translateY(${codeYIn}px)`
              }}
            >
              {JSON.stringify(FILES[activeIndex].issue, null, 2)}
            </div>
          </div>
        </div>
      </div>

      {/* UI Board Visualization */}
      <div style={{ flex: 1, width: "100%", maxWidth: "448px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{
          backgroundColor: "var(--column)",
          padding: "24px",
          borderRadius: "12px",
          position: "relative",
          overflow: "hidden",
          height: "100%",
          minHeight: "340px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center"
        }}>
          <div style={{ position: "relative", height: "100%", width: "100%" }}>
            {FILES.map((file, idx) => {
              const isActive = activeIndex === idx;

              const prevActiveIndex = (activeIndex - 1 + FILES.length) % FILES.length;

              const getTargetValues = (activeIdx: number) => {
                let yOffsetNum = 0;
                let scale = 0.95;
                let opacity = 0.5;
                let zIndex = 5;

                if (activeIdx === idx) {
                  yOffsetNum = 0;
                  scale = 1.05;
                  opacity = 1;
                  zIndex = 10;
                } else {
                  const isPrevious = (idx === activeIdx - 1) || (activeIdx === 0 && idx === FILES.length - 1);
                  yOffsetNum = isPrevious ? -90 : 90;
                }

                return { yOffsetNum, scale, opacity, zIndex };
              };

              const oldState = getTargetValues(prevActiveIndex);
              const newState = getTargetValues(activeIndex);

              const currentY = interpolate(boardSpring, [0, 1], [oldState.yOffsetNum, newState.yOffsetNum]);
              const currentScale = interpolate(boardSpring, [0, 1], [oldState.scale, newState.scale]);
              const currentOpacity = interpolate(boardSpring, [0, 1], [oldState.opacity, newState.opacity]);
              const currentZIndex = newState.zIndex;

              return (
                <div
                  key={file.filename}
                  style={{
                    position: "absolute",
                    width: "100%",
                    left: 0,
                    top: "50%",
                    transform: `translateY(calc(-50% + ${currentY}px)) scale(${currentScale})`,
                    opacity: currentOpacity,
                    zIndex: currentZIndex,
                  }}
                >
                  <IssueCard
                    issue={file.issue as any}
                    config={boardConfig as any}
                    priorityName={priorityLookup[file.issue.priority as keyof typeof priorityLookup]}
                    isSelected={isActive}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
