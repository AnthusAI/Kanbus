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

export function LocalTasksDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stage1End = fps * 2;
  const stage2End = fps * 4;

  const privateOpacity = interpolate(frame, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const cmdOpacity = interpolate(frame, [stage1End, stage1End + 10, stage2End - 10, stage2End], [0, 1, 1, 0]);
  const cmdString = "kanbus promote local-1a2b3c";
  const cmdChars = Math.floor(interpolate(frame, [stage1End + 10, stage1End + fps], [0, cmdString.length], { extrapolateRight: "clamp" }));

  const cardSpring = spring({
    frame: Math.max(0, frame - stage2End),
    fps,
    config: { damping: 15 }
  });

  const cardX = interpolate(cardSpring, [0, 1], [-200, 200]);
  const cardScale = interpolate(cardSpring, [0, 0.5, 1], [1, 1.1, 1]);

  const issue = { id: "PROJ-8b9c0d", title: "Spike: try the new auth library", type: "task", priority: 3, status: "in_progress" };

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

      {/* Background Zones */}
      <div style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: "64px",
        padding: "0 64px",
        zIndex: 10
      }}>
        <div style={{
          width: "50%",
          height: "400px",
          border: "2px dashed var(--text-muted)",
          borderRadius: "24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "flex-start",
          padding: "24px",
          backgroundColor: "var(--card)"
        }}>
          <h3 style={{ fontSize: "20px", fontWeight: "bold", color: "var(--text-foreground)", marginBottom: "8px" }}>project-local/</h3>
          <p style={{ fontSize: "14px", color: "var(--text-muted)" }}>(gitignored)</p>
        </div>
        <div style={{
          width: "50%",
          height: "400px",
          border: "2px solid var(--text-selected)",
          opacity: 0.5,
          borderRadius: "24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "flex-start",
          padding: "24px",
          backgroundColor: "var(--column)"
        }}>
          <h3 style={{ fontSize: "20px", fontWeight: "bold", color: "#60a5fa", marginBottom: "8px" }}>project/</h3>
          <p style={{ fontSize: "14px", color: "var(--text-selected)", opacity: 0.7 }}>(shared)</p>
        </div>
      </div>

      {/* Stage 2: CLI Sync */}
      <div style={{
        position: "absolute",
        width: "100%",
        maxWidth: "672px",
        backgroundColor: "var(--card)",
        borderRadius: "12px",
        overflow: "hidden",
        fontFamily: "monospace",
        fontSize: "18px",
        zIndex: 20,
        opacity: cmdOpacity
      }}>
        <div style={{
          padding: "24px",
          height: "100px",
          display: "flex",
          alignItems: "center",
          color: "#4ade80"
        }}>
          <span style={{ color: "#60a5fa", marginRight: "8px" }}>~</span>
          <span style={{ color: "#f472b6", marginRight: "8px" }}>❯</span>
          <span style={{ color: "#ffffff" }}>
            {cmdString.substring(0, Math.max(0, cmdChars))}
            <span style={{
              width: "10px",
              height: "20px",
              backgroundColor: "rgba(255,255,255,0.7)",
              display: "inline-block",
              marginLeft: "4px",
              verticalAlign: "middle"
            }} />
          </span>
        </div>
      </div>

      {/* The Issue Card */}
      <div style={{
        position: "absolute",
        width: "256px",
        zIndex: 10,
        transform: `translateX(${cardX}px) scale(${cardScale})`,
        opacity: privateOpacity
      }}>
        <IssueCard
          issue={issue as any}
          config={boardConfig as any}
          priorityName={"low"}
          isSelected={frame >= stage2End && frame <= stage2End + fps}
        />
      </div>
    </div>
  );
}
