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

  // Animation sequence
  // 1. Show Jira API Logo/Icon -> Arrow -> Kanbus Logo
  // 2. Command: kanbus jira sync
  // 3. Output files generating
  // 4. Show the issue cards appearing

  const stage1End = fps * 2;
  const stage2End = fps * 4;
  const stage3End = fps * 6;

  // Stage 1: API sync
  const apiOpacity = interpolate(frame, [0, 10, stage1End - 10, stage1End], [0, 1, 1, 0]);
  
  // Stage 2: CLI Command
  const cmdOpacity = interpolate(frame, [stage1End, stage1End + 10, stage2End - 10, stage2End], [0, 1, 1, 0]);
  const cmdString = "kanbus jira sync";
  const cmdChars = Math.floor(interpolate(frame, [stage1End + 10, stage1End + fps], [0, cmdString.length], { extrapolateRight: "clamp" }));

  // Stage 3: File generation
  const filesOpacity = interpolate(frame, [stage2End, stage2End + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const issues = [
    { id: "ENG-101", title: "Support single sign-on", type: "epic", priority: 1, status: "in_progress" },
    { id: "ENG-102", title: "Add Okta provider", type: "story", priority: 2, status: "backlog" },
    { id: "ENG-103", title: "Fix token expiration", type: "bug", priority: 1, status: "backlog" },
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
      
      {/* Stage 1: Sync Concept */}
      <div 
        className="absolute flex items-center gap-12 z-10"
        style={{ opacity: apiOpacity }}
      >
        <div className="w-32 h-32 bg-[var(--column)] border-2 border-dashed border-[var(--text-selected)] rounded-2xl flex items-center justify-center shadow-2xl">
          <span className="text-white font-bold text-2xl">Jira</span>
        </div>
        
        <div className="text-4xl text-[var(--text-foreground)]">
          <div className="animate-pulse">→</div>
        </div>

        <div className="w-32 h-32 bg-[var(--card)] rounded-2xl flex items-center justify-center shadow-2xl">
          <span className="text-white font-bold text-2xl">Kanbus</span>
        </div>
      </div>

      {/* Stage 2: CLI Sync */}
      <div 
        className="absolute w-full max-w-2xl bg-[var(--card)] rounded-xl overflow-hidden shadow-2xl font-mono text-lg z-10"
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

      {/* Stage 3: Cards Appeared */}
      <div 
        className="absolute flex gap-6 z-10"
        style={{ opacity: filesOpacity }}
      >
        {issues.map((issue, idx) => {
          // Cascade their appearance
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
              className="w-64"
              style={{ transform: `translateY(${y}px)`, opacity }}
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
