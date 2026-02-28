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

export function VirtualProjectsDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stage1End = fps * 2;
  const stage2End = fps * 4;

  const depsOpacity = interpolate(frame, [0, fps], [0, 1], { extrapolateRight: "clamp" });
  const depsY = interpolate(frame, [0, fps], [50, 0], { extrapolateRight: "clamp" });

  const mergeProgress = spring({
    frame: Math.max(0, frame - stage1End),
    fps,
    config: { damping: 15 }
  });

  const mainX = interpolate(mergeProgress, [0, 1], [-200, 0]);
  const dep1X = interpolate(mergeProgress, [0, 1], [200, 0]);
  const dep2X = interpolate(mergeProgress, [0, 1], [400, 0]);

  const boardOpacity = interpolate(frame, [stage2End, stage2End + fps], [0, 1], { extrapolateRight: "clamp" });
  const rawOpacity = interpolate(frame, [stage2End, stage2End + fps], [1, 0], { extrapolateRight: "clamp" });

  const issues = [
    { id: "API-01", title: "Update authentication endpoints", type: "story", priority: 1, status: "in_progress" },
    { id: "UI-42", title: "Redesign login screen", type: "epic", priority: 2, status: "backlog" },
    { id: "LIB-99", title: "Fix memory leak in parser", type: "bug", priority: 1, status: "in_progress" },
  ];

  const repoBoxStyle: React.CSSProperties = {
    width: "192px",
    height: "256px",
    borderRadius: "12px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    position: "relative"
  };

  return (
    <div style={{
      position: "absolute",
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      padding: "32px",
      height: "500px",
      ...(style || { inset: 0 })
    }}>
      {/* Background glow */}
      <div style={{
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        width: "800px",
        height: "400px",
        borderRadius: "100%",
        pointerEvents: "none",
        background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
      }} />

      {/* Raw Repositories View */}
      <div style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: "64px",
        opacity: rawOpacity
      }}>
        <div style={{
          ...repoBoxStyle,
          border: "1px solid rgba(59,130,246,0.5)",
          backgroundColor: "rgba(30,58,138,0.2)",
          transform: `translateX(${mainX}px)`
        }}>
          <div style={{ color: "#60a5fa", fontFamily: "monospace", fontWeight: "bold", marginBottom: "16px" }}>api-server/</div>
          <div style={{ fontSize: "12px", color: "var(--text-selected)", opacity: 0.7 }}>PROJ- API</div>
        </div>

        <div style={{
          ...repoBoxStyle,
          border: "1px solid rgba(168,85,247,0.5)",
          backgroundColor: "rgba(88,28,135,0.2)",
          transform: `translateX(${dep1X}px) translateY(${depsY}px)`,
          opacity: depsOpacity
        }}>
          <div style={{ color: "#c084fc", fontFamily: "monospace", fontWeight: "bold", marginBottom: "16px" }}>web-client/</div>
          <div style={{ fontSize: "12px", color: "rgba(168,85,247,0.7)" }}>PROJ- UI</div>
        </div>

        <div style={{
          ...repoBoxStyle,
          border: "1px solid rgba(34,197,94,0.5)",
          backgroundColor: "rgba(20,83,45,0.2)",
          transform: `translateX(${dep2X}px) translateY(${depsY}px)`,
          opacity: depsOpacity
        }}>
          <div style={{ color: "#4ade80", fontFamily: "monospace", fontWeight: "bold", marginBottom: "16px" }}>core-lib/</div>
          <div style={{ fontSize: "12px", color: "rgba(34,197,94,0.7)" }}>PROJ- LIB</div>
        </div>
      </div>

      {/* Unified Board View */}
      <div style={{
        position: "absolute",
        width: "100%",
        maxWidth: "896px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        opacity: boardOpacity
      }}>
        <div style={{
          textAlign: "center",
          color: "var(--text-foreground)",
          fontFamily: "monospace",
          marginBottom: "16px",
          fontSize: "14px",
          letterSpacing: "0.1em",
          textTransform: "uppercase"
        }}>
          Unified Workspace
        </div>
        <div style={{ display: "flex", gap: "24px", justifyContent: "center" }}>
          {issues.map((issue) => (
            <div key={issue.id} style={{ width: "256px" }}>
              <IssueCard
                issue={issue as any}
                config={boardConfig as any}
                priorityName={issue.priority === 1 ? "high" : "medium"}
                isSelected={false}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
