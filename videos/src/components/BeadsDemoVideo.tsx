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

export function BeadsDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const flipStart = fps * 3;
  const flipDuration = fps * 1.5;

  const flipProgress = interpolate(frame, [flipStart, flipStart + flipDuration], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const rotateY = interpolate(flipProgress, [0, 1], [0, 180]);

  const showFront = rotateY <= 90;

  const beadsMarkdown = `---
title: Update logo on landing page
type: task
status: in_progress
priority: medium
assignee: ryan
---

We need to update the logo on the landing page to match the new branding guidelines.

- [ ] Download new SVG
- [ ] Replace existing asset
- [ ] Check responsive sizes
`;

  const issue = { id: "BD-123", title: "Update logo on landing page", type: "task", priority: 2, status: "in_progress", assignee: "ryan" };

  return (
    <div style={{
      position: "absolute",
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      padding: "32px",
      height: "500px",
      perspective: 1000,
      ...(style || { inset: 0 })
    }}>
      <div style={{
        width: "400px",
        height: "300px",
        position: "relative",
        transformStyle: "preserve-3d",
        transform: `rotateY(${rotateY}deg)`
      }}>
        {/* Front: Markdown File */}
        {showFront && (
          <div style={{
            position: "absolute",
            inset: 0,
            backgroundColor: "var(--card)",
            borderRadius: "12px",
            overflow: "hidden",
            padding: "24px",
            border: "1px solid var(--border)",
            backfaceVisibility: "hidden"
          }}>
            <div style={{
              color: "var(--text-foreground)",
              fontFamily: "monospace",
              fontSize: "14px",
              marginBottom: "16px",
              borderBottom: "1px solid #404040",
              paddingBottom: "8px"
            }}>BD-123.md</div>
            <pre style={{
              color: "#4ade80",
              fontFamily: "monospace",
              fontSize: "12px",
              whiteSpace: "pre-wrap",
              lineHeight: "1.625"
            }}>
              {beadsMarkdown}
            </pre>
          </div>
        )}

        {/* Back: Kanbus Card */}
        {!showFront && (
          <div style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backfaceVisibility: "hidden",
            transform: "rotateY(180deg)"
          }}>
            <div style={{ width: "100%" }}>
              <IssueCard
                issue={issue as any}
                config={boardConfig as any}
                priorityName={"medium"}
                isSelected={true}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
