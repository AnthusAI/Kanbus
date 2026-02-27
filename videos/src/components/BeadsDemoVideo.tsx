import * as React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "../remotion-shim";
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

  // Sequence:
  // 1. Show raw markdown file (Beads format)
  // 2. File morphs/flips into an interactive Kanban board card

  const flipStart = fps * 3;
  const flipDuration = fps * 1.5;

  const flipProgress = interpolate(frame, [flipStart, flipStart + flipDuration], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  
  // Rotation for the 3D flip effect
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
    <div className="absolute flex justify-center items-center p-8 h-[500px]" style={{ perspective: 1000, ...(style || { inset: 0 }) }}>
      
      <div 
        className="w-[400px] h-[300px] relative transition-transform"
        style={{ 
          transformStyle: "preserve-3d",
          transform: `rotateY(${rotateY}deg)`,
        }}
      >
        {/* Front: Markdown File */}
        {showFront && (
          <div 
            className="absolute inset-0 bg-[var(--card)] rounded-xl overflow-hidden shadow-2xl p-6 border border-border"
            style={{ backfaceVisibility: "hidden" }}
          >
            <div className="text-[var(--text-foreground)] font-mono text-sm mb-4 border-b border-neutral-700 pb-2">BD-123.md</div>
            <pre className="text-green-400 font-mono text-xs whitespace-pre-wrap leading-relaxed">
              {beadsMarkdown}
            </pre>
          </div>
        )}

        {/* Back: Kanbus Card */}
        {!showFront && (
          <div 
            className="absolute inset-0 flex items-center justify-center"
            style={{ 
              backfaceVisibility: "hidden", 
              transform: "rotateY(180deg)" 
            }}
          >
            <div className="w-full">
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
