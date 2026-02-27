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

  // Animation timeline:
  // 1. Show private workspace (local task)
  // 2. Command: kanbus promote
  // 3. Issue moves to shared workspace

  const stage1End = fps * 2;
  const stage2End = fps * 4;

  // Stage 1: Private workspace
  const privateOpacity = interpolate(frame, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // Stage 2: CLI Command
  const cmdOpacity = interpolate(frame, [stage1End, stage1End + 10, stage2End - 10, stage2End], [0, 1, 1, 0]);
  const cmdString = "kanbus promote local-1a2b3c";
  const cmdChars = Math.floor(interpolate(frame, [stage1End + 10, stage1End + fps], [0, cmdString.length], { extrapolateRight: "clamp" }));

  // Stage 3: Promotion transition
  const cardSpring = spring({
    frame: Math.max(0, frame - stage2End),
    fps,
    config: { damping: 15 }
  });
  
  // Card moves from left (private) to right (shared)
  const cardX = interpolate(cardSpring, [0, 1], [-200, 200]);
  const cardScale = interpolate(cardSpring, [0, 0.5, 1], [1, 1.1, 1]);

  const issue = { id: "PROJ-8b9c0d", title: "Spike: try the new auth library", type: "task", priority: 3, status: "in_progress" };

  return (
    <div className="absolute flex justify-center items-center p-8 h-[500px]" style={style || { inset: 0 }}>
      {/* Background glow to ground the 3D window */}
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] rounded-[100%] pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
        }}
      />
      
      {/* Background Zones */}
      <div className="absolute inset-0 flex justify-center items-center gap-16 px-16 z-10">
        <div className="w-1/2 h-[400px] border-2 border-dashed border-[var(--text-muted)] rounded-3xl flex flex-col items-center justify-start p-6 bg-[var(--card)]">
          <h3 className="text-xl font-bold text-[var(--text-foreground)] mb-2">project-local/</h3>
          <p className="text-sm text-[var(--text-muted)]">(gitignored)</p>
        </div>
        <div className="w-1/2 h-[400px] border-2 border-solid border-[var(--text-selected)] opacity-50 rounded-3xl flex flex-col items-center justify-start p-6 bg-[var(--column)]">
          <h3 className="text-xl font-bold text-blue-400 mb-2">project/</h3>
          <p className="text-sm text-[var(--text-selected)] opacity-70">(shared)</p>
        </div>
      </div>

      {/* Stage 2: CLI Sync */}
      <div 
        className="absolute w-full max-w-2xl bg-[var(--card)] rounded-xl overflow-hidden shadow-2xl font-mono text-lg z-20"
        style={{ opacity: cmdOpacity }}
      >
        <div className="p-6 h-[100px] flex items-center text-green-400">
          <span className="text-blue-400 mr-2">~</span>
          <span className="text-pink-400 mr-2">❯</span>
          <span className="text-white">
            {cmdString.substring(0, Math.max(0, cmdChars))}
            <span className="w-2.5 h-5 bg-white/70 inline-block ml-1 align-middle animate-pulse"></span>
          </span>
        </div>
      </div>

      {/* The Issue Card */}
      <div 
        className="absolute w-64 z-10"
        style={{ 
          transform: `translateX(${cardX}px) scale(${cardScale})`, 
          opacity: privateOpacity 
        }}
      >
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
