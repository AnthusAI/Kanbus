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

  // Animation timeline:
  // 1. Show main repo
  // 2. Show separate dependency repos sliding in
  // 3. Command: kanbus list --all (or similar)
  // 4. They all merge into one unified board/list

  const stage1End = fps * 2;
  const stage2End = fps * 4;

  // Stage 1: Dependency Repos slide in
  const depsOpacity = interpolate(frame, [0, fps], [0, 1], { extrapolateRight: "clamp" });
  const depsY = interpolate(frame, [0, fps], [50, 0], { extrapolateRight: "clamp" });

  // Stage 2: Merge into one
  const mergeProgress = spring({
    frame: Math.max(0, frame - stage1End),
    fps,
    config: { damping: 15 }
  });

  const mainX = interpolate(mergeProgress, [0, 1], [-200, 0]);
  const dep1X = interpolate(mergeProgress, [0, 1], [200, 0]);
  const dep2X = interpolate(mergeProgress, [0, 1], [400, 0]);

  // Stage 3: Fade out raw blocks, fade in unified board
  const boardOpacity = interpolate(frame, [stage2End, stage2End + fps], [0, 1], { extrapolateRight: "clamp" });
  const rawOpacity = interpolate(frame, [stage2End, stage2End + fps], [1, 0], { extrapolateRight: "clamp" });

  const issues = [
    { id: "API-01", title: "Update authentication endpoints", type: "story", priority: 1, status: "in_progress" },
    { id: "UI-42", title: "Redesign login screen", type: "epic", priority: 2, status: "backlog" },
    { id: "LIB-99", title: "Fix memory leak in parser", type: "bug", priority: 1, status: "in_progress" },
  ];

  return (
    <div className="absolute flex justify-center items-center p-8 h-[500px]" style={style || { inset: 0 }}>
      {/* Background glow to ground the 3D window */}
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] rounded-[100%] pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
        }}
      />
      
      {/* Raw Repositories View */}
      <div 
        className="absolute inset-0 flex justify-center items-center gap-16"
        style={{ opacity: rawOpacity }}
      >
        <div 
          className="w-48 h-64 border border-blue-500/50 bg-blue-900/20 rounded-xl flex flex-col items-center justify-center relative"
          style={{ transform: `translateX(${mainX}px)` }}
        >
          <div className="text-blue-400 font-mono font-bold mb-4">api-server/</div>
          <div className="text-xs text-[var(--text-selected)] opacity-70">PROJ- API</div>
        </div>

        <div 
          className="w-48 h-64 border border-purple-500/50 bg-purple-900/20 rounded-xl flex flex-col items-center justify-center relative"
          style={{ transform: `translateX(${dep1X}px)`, opacity: depsOpacity, translateY: `${depsY}px` }}
        >
          <div className="text-purple-400 font-mono font-bold mb-4">web-client/</div>
          <div className="text-xs text-purple-500/70">PROJ- UI</div>
        </div>

        <div 
          className="w-48 h-64 border border-green-500/50 bg-green-900/20 rounded-xl flex flex-col items-center justify-center relative"
          style={{ transform: `translateX(${dep2X}px)`, opacity: depsOpacity, translateY: `${depsY}px` }}
        >
          <div className="text-green-400 font-mono font-bold mb-4">core-lib/</div>
          <div className="text-xs text-green-500/70">PROJ- LIB</div>
        </div>
      </div>

      {/* Unified Board View */}
      <div 
        className="absolute w-full max-w-4xl flex flex-col gap-4"
        style={{ opacity: boardOpacity }}
      >
        <div className="text-center text-[var(--text-foreground)] font-mono mb-4 text-sm tracking-widest uppercase">
          Unified Workspace
        </div>
        <div className="flex gap-6 justify-center">
          {issues.map((issue) => (
            <div key={issue.id} className="w-64">
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
