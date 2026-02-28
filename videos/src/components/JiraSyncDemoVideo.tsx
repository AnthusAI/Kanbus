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

export function JiraSyncDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stage1End = fps * 2;
  const stage2End = fps * 4;

  const apiOpacity = interpolate(frame, [0, 10, stage1End - 10, stage1End], [0, 1, 1, 0]);

  const cmdOpacity = interpolate(frame, [stage1End, stage1End + 10, stage2End - 10, stage2End], [0, 1, 1, 0]);
  const cmdString = "kanbus jira sync";
  const cmdChars = Math.floor(interpolate(frame, [stage1End + 10, stage1End + fps], [0, cmdString.length], { extrapolateRight: "clamp" }));

  const filesOpacity = interpolate(frame, [stage2End, stage2End + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const issues = [
    { id: "ENG-101", title: "Support single sign-on", type: "epic", priority: 1, status: "in_progress" },
    { id: "ENG-102", title: "Add Okta provider", type: "story", priority: 2, status: "backlog" },
    { id: "ENG-103", title: "Fix token expiration", type: "bug", priority: 1, status: "backlog" },
  ];

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

      {/* Stage 1: Sync Concept */}
      <div style={{
        position: "absolute",
        display: "flex",
        alignItems: "center",
        gap: "48px",
        zIndex: 10,
        opacity: apiOpacity
      }}>
        <div style={{
          width: "128px",
          height: "128px",
          backgroundColor: "var(--column)",
          border: "2px dashed var(--text-selected)",
          borderRadius: "16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 25px 50px -12px rgba(0,0,0,0.25)"
        }}>
          <span style={{ color: "#ffffff", fontWeight: "bold", fontSize: "24px" }}>Jira</span>
        </div>

        <div style={{ fontSize: "36px", color: "var(--text-foreground)" }}>
          <div>→</div>
        </div>

        <div style={{
          width: "128px",
          height: "128px",
          backgroundColor: "var(--card)",
          borderRadius: "16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 25px 50px -12px rgba(0,0,0,0.25)"
        }}>
          <span style={{ color: "#ffffff", fontWeight: "bold", fontSize: "24px" }}>Kanbus</span>
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
        zIndex: 10,
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

      {/* Stage 3: Cards Appeared */}
      <div style={{
        position: "absolute",
        display: "flex",
        gap: "24px",
        zIndex: 10,
        opacity: filesOpacity
      }}>
        {issues.map((issue, idx) => {
          const delay = idx * (fps * 0.3);
          const cardSpring = spring({
            frame: Math.max(0, frame - stage2End - delay),
            fps,
            config: { damping: 15 }
          });
          const y = interpolate(cardSpring, [0, 1], [50, 0]);
          const opacity = interpolate(cardSpring, [0, 1], [0, 1]);

          return (
            <div
              key={issue.id}
              style={{ width: "256px", transform: `translateY(${y}px)`, opacity }}
            >
              <IssueCard
                issue={issue as any}
                config={boardConfig as any}
                priorityName={issue.priority === 1 ? "high" : "medium"}
                isSelected={false}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
