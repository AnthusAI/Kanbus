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

const priorityLookup = {
  1: "high",
  2: "medium",
  3: "low"
};

const FILES = [
  {
    filename: "issues/PROJ-1a2b3c.json",
    issue: {
      id: "PROJ-1a2b3c",
      title: "Calibrate flux capacitor",
      type: "epic",
      status: "backlog",
      priority: 2,
      assignee: "Codex",
    }
  },
  {
    filename: "issues/PROJ-4d5e6f.json",
    issue: {
      id: "PROJ-4d5e6f",
      title: "Stabilize warp core coolant loop",
      type: "task",
      status: "in_progress",
      priority: 1,
      assignee: "Ryan",
    }
  },
  {
    filename: "issues/PROJ-7g8h9i.json",
    issue: {
      id: "PROJ-7g8h9i",
      title: "Diagnose tachyon scanner drift",
      type: "bug",
      status: "in_progress",
      priority: 1,
      assignee: "Claude",
    }
  }
];

export function CodeUiSyncVideo() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Change every 4.5 seconds
  const intervalFrames = fps * 4.5;
  const activeIndex = Math.floor(frame / intervalFrames) % FILES.length;
  const transitionFrame = frame % intervalFrames;

  // Animate the code block (opacity and y shift on change)
  // Transition lasts 0.2s = 0.2 * fps frames
  const transitionDuration = fps * 0.2;
  const codeOpacityIn = interpolate(transitionFrame, [0, transitionDuration], [0, 1], { extrapolateRight: "clamp" });
  const codeYIn = interpolate(transitionFrame, [0, transitionDuration], [10, 0], { extrapolateRight: "clamp" });
  
  // Actually, we can use a spring for the board items as they shift
  const boardSpring = spring({
    frame: transitionFrame,
    fps,
    config: {
      damping: 30,
      stiffness: 300,
    }
  });

  return (
    <div className="w-full flex flex-col md:flex-row gap-8 items-stretch justify-center relative p-8">
      {/* Code Window */}
      <div className="flex-1 w-full max-w-xl">
        <div className="bg-card rounded-xl font-mono text-sm leading-loose overflow-hidden shadow-2xl h-full flex flex-col">
          <div className="text-muted flex items-center gap-4 bg-card-muted p-4 border-b border-border">
             <div className="flex gap-2">
               <span className="w-3 h-3 rounded-full bg-red-500/50"></span>
               <span className="w-3 h-3 rounded-full bg-yellow-500/50"></span>
               <span className="w-3 h-3 rounded-full bg-green-500/50"></span>
             </div>
             <div className="flex flex-1 gap-2 overflow-x-auto hide-scrollbar">
               {FILES.map((file, idx) => (
                 <div 
                   key={file.filename}
                   className={`px-3 py-1 rounded-md text-xs whitespace-nowrap transition-colors ${activeIndex === idx ? 'bg-background text-foreground shadow-sm' : 'text-muted'}`}
                 >
                   {file.filename.split('/')[1]}
                 </div>
               ))}
             </div>
          </div>
          
          <div className="relative h-[260px] p-6">
            <div
              style={{
                position: "absolute",
                inset: 0,
                padding: "1.5rem",
                overflow: "hidden",
                whiteSpace: "pre",
                color: "var(--foreground)",
                opacity: codeOpacityIn,
                transform: `translateY(${codeYIn}px)`
              }}
            >
              {JSON.stringify(FILES[activeIndex].issue, null, 2)}
            </div>
          </div>
        </div>
      </div>
      
      {/* UI Board Visualization */}
      <div className="flex-1 w-full max-w-xl md:max-w-sm flex flex-col justify-center">
        <div className="bg-column p-4 md:p-6 rounded-xl relative overflow-hidden h-full min-h-[340px] flex flex-col justify-center">
          
          <div className="relative h-full w-full">
            {FILES.map((file, idx) => {
              const isActive = activeIndex === idx;
              
              // We'll calculate the old states and new states to interpolate
              // For simplicity, we just calculate the target state, and use spring for transition
              // The previous active index is (activeIndex - 1 + FILES.length) % FILES.length
              const prevActiveIndex = (activeIndex - 1 + FILES.length) % FILES.length;
              const isPrevActive = prevActiveIndex === idx;

              const getTargetValues = (activeIdx: number) => {
                let yOffsetNum = 0;
                let scale;
                let opacity = 0.5;
                let zIndex = 0;
                if (activeIdx === idx) {
                  yOffsetNum = 0;
                  scale = 1.05;
                  opacity = 1;
                  zIndex = 10;
                } else {
                  const isPrevious = (idx === activeIdx - 1) || (activeIdx === 0 && idx === FILES.length - 1);
                  if (isPrevious) {
                    yOffsetNum = -90;
                    scale = 0.95;
                    opacity = 0.5;
                    zIndex = 5;
                  } else {
                    yOffsetNum = 90;
                    scale = 0.95;
                    opacity = 0.5;
                    zIndex = 5;
                  }
                }
                return { yOffsetNum, scale, opacity, zIndex };
              };

              const oldState = getTargetValues(prevActiveIndex);
              const newState = getTargetValues(activeIndex);

              const currentY = interpolate(boardSpring, [0, 1], [oldState.yOffsetNum, newState.yOffsetNum]);
              const currentScale = interpolate(boardSpring, [0, 1], [oldState.scale, newState.scale]);
              const currentOpacity = interpolate(boardSpring, [0, 1], [oldState.opacity, newState.opacity]);

              // Use new zIndex immediately
              const currentZIndex = newState.zIndex;

              return (
                <div
                  key={file.filename}
                  style={{
                    position: "absolute",
                    width: "100%",
                    left: 0,
                    top: "50%",
                    transform: `translateY(calc(-50% + ${currentY}px)) scale(${currentScale})`,
                    opacity: currentOpacity,
                    zIndex: currentZIndex,
                  }}
                >
                  <IssueCard 
                    issue={file.issue as any}
                    config={boardConfig as any}
                    priorityName={priorityLookup[file.issue.priority as keyof typeof priorityLookup]}
                    isSelected={isActive}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
