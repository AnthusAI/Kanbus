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

export function VsCodeDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const clickFrame = fps * 2;
  const boardOpenFrame = fps * 3;

  const pointerX = interpolate(frame, [0, clickFrame], [800, 25], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const pointerY = interpolate(frame, [0, clickFrame], [400, 150], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const pointerScale = interpolate(frame, [clickFrame - 5, clickFrame, clickFrame + 5], [1, 0.8, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const isBoardOpen = frame >= boardOpenFrame;
  const boardScale = spring({
    frame: Math.max(0, frame - boardOpenFrame),
    fps,
    config: { damping: 15 }
  });

  const dummyCode = `function syncWithJira() {
  const issues = fetchJiraIssues();
  for (const issue of issues) {
    writeToLocal(issue);
  }
  return true;
}`;

  const issue = { id: "VS-99", title: "Add drag and drop to board", type: "task", priority: 1, status: "in_progress", assignee: "ryan" };

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
        width: "900px",
        height: "500px",
        borderRadius: "100%",
        pointerEvents: "none",
        background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
      }} />

      {/* Fake VS Code Window */}
      <div style={{
        width: "100%",
        maxWidth: "1024px",
        height: "400px",
        backgroundColor: "var(--card)",
        borderRadius: "12px",
        overflow: "hidden",
        display: "flex",
        border: "1px solid var(--border)",
        position: "relative",
        zIndex: 10
      }}>

        {/* Activity Bar */}
        <div style={{
          width: "56px",
          backgroundColor: "#333333",
          borderRight: "1px solid rgba(0,0,0,0.5)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "16px 0",
          gap: "24px",
          zIndex: 10
        }}>
          <div style={{
            width: "32px",
            height: "32px",
            borderRadius: "4px",
            color: "var(--text-foreground)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
          </div>
          <div style={{
            width: "32px",
            height: "32px",
            borderRadius: "4px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: isBoardOpen ? "var(--column)" : "transparent",
            border: isBoardOpen ? "2px dashed var(--text-selected)" : "none",
            color: isBoardOpen ? "#ffffff" : "var(--text-foreground)"
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
          </div>
        </div>

        {/* Sidebar */}
        <div style={{
          width: "256px",
          backgroundColor: "#252526",
          borderRight: "1px solid rgba(0,0,0,0.5)",
          padding: "16px"
        }}>
          <div style={{
            fontSize: "12px",
            fontWeight: "bold",
            color: "var(--text-foreground)",
            letterSpacing: "0.1em",
            marginBottom: "16px"
          }}>EXPLORER</div>
          <div style={{ fontSize: "14px", color: "#d4d4d4" }}>
            <div style={{ marginBottom: "8px" }}><span style={{ marginRight: "8px" }}>src</span></div>
            <div style={{ paddingLeft: "16px", marginBottom: "8px" }}><span style={{ marginRight: "8px", color: "#60a5fa" }}>sync.ts</span></div>
            <div style={{ paddingLeft: "16px", marginBottom: "8px" }}><span style={{ marginRight: "8px", color: "#60a5fa" }}>cli.ts</span></div>
            <div style={{ paddingLeft: "16px", marginBottom: "8px" }}><span style={{ marginRight: "8px", color: "#60a5fa" }}>index.ts</span></div>
          </div>
        </div>

        {/* Editor Area */}
        <div style={{
          flex: 1,
          backgroundColor: "var(--card)",
          display: "flex",
          flexDirection: "column",
          position: "relative",
          overflow: "hidden"
        }}>
          {/* Tabs */}
          <div style={{
            display: "flex",
            backgroundColor: "var(--card-muted)",
            height: "40px",
            borderBottom: "1px solid rgba(0,0,0,0.5)"
          }}>
            <div style={{
              padding: "8px 16px",
              backgroundColor: "var(--card)",
              color: "#60a5fa",
              fontSize: "14px",
              borderTop: "2px solid #3b82f6"
            }}>
              sync.ts
            </div>
            {isBoardOpen && (
              <div style={{
                padding: "8px 16px",
                backgroundColor: "var(--card)",
                color: "#4ade80",
                fontSize: "14px",
                borderTop: "2px solid #22c55e",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                transform: `scaleX(${boardScale})`,
                transformOrigin: "left"
              }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
                Kanbus Board
              </div>
            )}
          </div>

          {/* Content */}
          <div style={{ padding: "24px", position: "relative", height: "100%" }}>
            {/* Code */}
            <div style={{
              fontFamily: "monospace",
              fontSize: "14px",
              color: "#d4d4d4",
              opacity: isBoardOpen ? 0 : 1,
              position: isBoardOpen ? "absolute" : "static"
            }}>
              <pre dangerouslySetInnerHTML={{ __html: dummyCode.replace(/syncWithJira/g, '<span style="color:#fef08a">syncWithJira</span>').replace(/function/g, '<span style="color:#60a5fa">function</span>').replace(/const/g, '<span style="color:#60a5fa">const</span>') }} />
            </div>

            {/* Board */}
            {isBoardOpen && (
              <div style={{
                position: "absolute",
                inset: 0,
                backgroundColor: "var(--card)",
                padding: "24px"
              }}>
                <div style={{ width: "288px" }}>
                  <IssueCard
                    issue={issue as any}
                    config={boardConfig as any}
                    priorityName={"high"}
                    isSelected={false}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Pointer / Cursor */}
        <div style={{
          position: "absolute",
          zIndex: 50,
          transform: `translate(${pointerX}px, ${pointerY}px) scale(${pointerScale})`
        }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="white" stroke="black" strokeWidth="1">
            <path d="M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 01.35-.15h6.42c.41 0 .62-.5.33-.78L5.5 3.21z" />
          </svg>
        </div>
      </div>
    </div>
  );
}
