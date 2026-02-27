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

  // Sequence:
  // 1. Show VS Code layout (sidebar left, code right)
  // 2. Click "Kanbus" icon
  // 3. Tab opens with Kanbus board instead of code

  const clickFrame = fps * 2;
  const boardOpenFrame = fps * 3;

  // Pointer position
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
    <div className="absolute flex justify-center items-center p-8 h-[500px]" style={style || { inset: 0 }}>
      {/* Background glow to ground the 3D window */}
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[500px] rounded-[100%] pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
        }}
      />
      
      {/* Fake VS Code Window */}
      <div className="w-full max-w-5xl h-[400px] bg-[var(--card)] rounded-xl overflow-hidden shadow-2xl flex border border-border relative z-10">
        
        {/* Activity Bar */}
        <div className="w-14 bg-[#333333] border-r border-black/50 flex flex-col items-center py-4 gap-6 z-10">
          <div className="w-8 h-8 rounded text-[var(--text-foreground)] flex items-center justify-center">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
          </div>
          <div className={`w-8 h-8 rounded flex items-center justify-center transition-colors ${isBoardOpen ? 'bg-[var(--column)] border-2 border-dashed border-[var(--text-selected)] text-white' : 'text-[var(--text-foreground)]'}`}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
          </div>
        </div>

        {/* Sidebar */}
        <div className="w-64 bg-[#252526] border-r border-black/50 p-4">
          <div className="text-xs font-bold text-[var(--text-foreground)] tracking-wider mb-4">EXPLORER</div>
          <div className="text-sm text-neutral-300 space-y-2">
            <div><span className="mr-2">📁</span>src</div>
            <div className="pl-4"><span className="mr-2 text-blue-400">📄</span>sync.ts</div>
            <div className="pl-4"><span className="mr-2 text-blue-400">📄</span>cli.ts</div>
            <div className="pl-4"><span className="mr-2 text-blue-400">📄</span>index.ts</div>
          </div>
        </div>

        {/* Editor Area */}
        <div className="flex-1 bg-[var(--card)] flex flex-col relative overflow-hidden">
          {/* Tabs */}
          <div className="flex bg-[var(--card-muted)] h-10 border-b border-black/50">
            <div className="px-4 py-2 bg-[var(--card)] text-blue-400 text-sm border-t-2 border-blue-500">
              sync.ts
            </div>
            {isBoardOpen && (
              <div 
                className="px-4 py-2 bg-[var(--card)] text-green-400 text-sm border-t-2 border-green-500 flex items-center gap-2"
                style={{ transform: `scaleX(${boardScale})`, transformOrigin: "left" }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
                Kanbus Board
              </div>
            )}
          </div>

          {/* Content */}
          <div className="p-6 relative h-full">
            {/* Code */}
            <div className={`font-mono text-sm text-neutral-300 transition-opacity ${isBoardOpen ? 'opacity-0 absolute' : 'opacity-100'}`}>
              <pre dangerouslySetInnerHTML={{ __html: dummyCode.replace(/syncWithJira/g, '<span class="text-yellow-200">syncWithJira</span>').replace(/function/g, '<span class="text-blue-400">function</span>').replace(/const/g, '<span class="text-blue-400">const</span>') }} />
            </div>

            {/* Board */}
            {isBoardOpen && (
              <div className="absolute inset-0 bg-[var(--card)] p-6">
                <div className="w-72">
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
        <div 
          className="absolute z-50 transition-transform"
          style={{ 
            transform: `translate(${pointerX}px, ${pointerY}px) scale(${pointerScale})`,
          }}
        >
          <svg width="32" height="32" viewBox="0 0 24 24" fill="white" stroke="black" strokeWidth="1">
            <path d="M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 01.35-.15h6.42c.41 0 .62-.5.33-.78L5.5 3.21z" />
          </svg>
        </div>

      </div>

    </div>
  );
}
