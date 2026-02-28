import * as React from "react";
import { useEffect, useState } from "react";
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

  const renderHighlightedJson = (issue: any) => {
    const json = JSON.stringify(issue, null, 2);
    const html = json
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        let cls = 'text-orange-400'; // number
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            cls = 'text-sky-400'; // key
          } else {
            cls = 'text-green-400'; // string
          }
        } else if (/true|false/.test(match)) {
          cls = 'text-pink-400'; // boolean
        } else if (/null/.test(match)) {
          cls = 'text-muted'; // null
        }
        return '<span class="' + cls + '">' + match + '</span>';
      });
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="w-full flex flex-col md:flex-row gap-8 items-stretch justify-center relative">
      {/* Background glow to ground the 3D window */}
      <div 
        className="absolute top-1/2 left-[25%] -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-[100%] pointer-events-none z-0"
        style={{
          background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
        }}
      />
      
      {/* Code Window */}
      <div className="flex-1 w-full md:max-w-md z-10">
        <div className="bg-card rounded-xl font-mono text-sm leading-loose overflow-hidden shadow-2xl h-full flex flex-col border border-border/50">
          <div className="text-muted flex items-center bg-card-muted px-3 py-2 border-b border-border/50">
             <div className="flex flex-1 gap-2 overflow-x-auto hide-scrollbar">
               {FILES.map((file, idx) => (
                 <div 
                   key={file.filename}
                   className={`px-3 py-1 rounded-md text-xs whitespace-nowrap transition-colors ${activeIndex === idx ? 'bg-background text-foreground shadow-sm border border-border/50' : 'text-muted hover:text-foreground cursor-pointer border border-transparent'}`}
                   onClick={() => setActiveIndex(idx)}
                 >
                   {file.filename.split('/')[1]}
                 </div>
               ))}
             </div>
          </div>
          
          <div className="relative h-[260px] p-6 bg-background">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeIndex}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0 p-6 overflow-hidden whitespace-pre text-foreground"
              >
                {renderHighlightedJson(FILES[activeIndex].issue)}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
      
      {/* UI Board Visualization */}
      <div className="flex-1 w-full max-w-xl md:max-w-lg flex flex-col justify-center z-10">
        <div className="bg-column p-4 md:p-6 rounded-xl relative overflow-hidden h-full min-h-[340px] flex flex-col justify-center">
          
          <div className="relative h-full w-full">
            {FILES.map((file, idx) => {
              const isActive = activeIndex === idx;
              
              // Calculate Y offset based on position relative to active item
              // This creates a carousel/stacking effect centered vertically
              let yOffsetNum = 0;
              let scale;
              let opacity;
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
