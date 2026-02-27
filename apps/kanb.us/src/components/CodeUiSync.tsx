import * as React from "react";
import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
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

export function CodeUiSync() {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    // Auto-play the tabs
    const interval = setInterval(() => {
      setActiveIndex((current) => (current + 1) % FILES.length);
    }, 4500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full flex flex-col md:flex-row gap-8 items-stretch justify-center relative">
      {/* Code Window */}
      <div className="flex-1 w-full max-w-xl">
        <div className="bg-card rounded-xl font-mono text-sm leading-loose overflow-hidden shadow-2xl h-full flex flex-col">
          <div className="text-muted flex items-center gap-4 bg-card-muted p-4 border-b border-border/20">
             <div className="flex gap-2">
               <span className="w-3 h-3 rounded-full bg-red-500/50"></span>
               <span className="w-3 h-3 rounded-full bg-yellow-500/50"></span>
               <span className="w-3 h-3 rounded-full bg-green-500/50"></span>
             </div>
             <div className="flex flex-1 gap-2 overflow-x-auto hide-scrollbar">
               {FILES.map((file, idx) => (
                 <div 
                   key={file.filename}
                   className={`px-3 py-1 rounded-md text-xs whitespace-nowrap transition-colors ${activeIndex === idx ? 'bg-background text-foreground shadow-sm' : 'text-muted hover:text-foreground cursor-pointer'}`}
                   onClick={() => setActiveIndex(idx)}
                 >
                   {file.filename.split('/')[1]}
                 </div>
               ))}
             </div>
          </div>
          
          <div className="relative h-[260px] p-6">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeIndex}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0 p-6 overflow-hidden whitespace-pre text-foreground"
              >
                {JSON.stringify(FILES[activeIndex].issue, null, 2)}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
      
      {/* UI Board Visualization */}
      <div className="flex-1 w-full max-w-xl md:max-w-sm flex flex-col justify-center">
        <div className="bg-column p-4 md:p-6 rounded-xl relative overflow-hidden h-full min-h-[340px] flex flex-col justify-center">
          
          <div className="relative h-full w-full">
            {FILES.map((file, idx) => {
              const isActive = activeIndex === idx;
              
              // Calculate Y offset based on position relative to active item
              // This creates a carousel/stacking effect centered vertically
              let yOffsetNum = 0;
              let scale = 1;
              let opacity = 1;
              let zIndex = 0;
              
              if (isActive) {
                yOffsetNum = 0;
                scale = 1.05;
                opacity = 1;
                zIndex = 10;
              } else {
                // If this item is before the active one (or wrap-around)
                const isPrevious = (idx === activeIndex - 1) || (activeIndex === 0 && idx === FILES.length - 1);
                
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

              return (
                <motion.div
                  key={file.filename}
                  animate={{
                    y: `calc(-50% + ${yOffsetNum}px)`,
                    scale,
                    opacity,
                    zIndex,
                  }}
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  className="absolute w-full left-0 top-1/2"
                >
                  <IssueCard 
                    issue={file.issue as any}
                    config={boardConfig as any}
                    priorityName={priorityLookup[file.issue.priority as keyof typeof priorityLookup]}
                    isSelected={isActive}
                  />
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
