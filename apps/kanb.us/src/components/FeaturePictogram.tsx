import * as React from "react";
import { motion } from "framer-motion";

export type FeaturePictogramType = 
  | "core-management" 
  | "kanban-board" 
  | "jira-sync" 
  | "local-tasks" 
  | "beads-compatibility" 
  | "virtual-projects" 
  | "vscode-plugin" 
  | "integrated-wiki" 
  | "policy-as-code";

export function FeaturePictogram({ type, style, className }: { type: string, style?: React.CSSProperties, className?: string }) {
  const Board = ({ x = 250, y, opacity = 1, color = "var(--column)" }: { x?: number; y: number; opacity?: number; color?: string }) => (
    <g transform={`translate(${x}, ${y}) scale(1, 0.5) rotate(45) translate(-100, -75)`} opacity={opacity}>
      {/* Board Base */}
      <rect width="200" height="150" fill={color} rx="8" />
      
      {/* Columns */}
      <rect x="10" y="10" width="54" height="130" fill="var(--background)" rx="4" />
      <rect x="73" y="10" width="54" height="130" fill="var(--background)" rx="4" />
      <rect x="136" y="10" width="54" height="130" fill="var(--background)" rx="4" />
    </g>
  );

  const renderCli = () => (
    <g transform="scale(1) translate(0, 0)">
      <defs>
        <clipPath id="cmd-clip">
          <rect x="56" y="70" width="0" height="40">
            <animate attributeName="width" values="0; 135; 135; 0" dur="6s" keyTimes="0; 0.15; 0.9; 1" repeatCount="indefinite" />
          </rect>
        </clipPath>
      </defs>

      {/* Terminal Window Flat */}
      <rect x="0" y="0" width="500" height="300" fill="var(--column)" rx="10" />
      
      {/* Terminal Header */}
      <rect x="0" y="0" width="500" height="40" fill="var(--background)" rx="10" />
      
      {/* MacOS Window Buttons */}
      <circle cx="24" cy="22" r="6" fill="#ff5f56" stroke="#e0443e" strokeWidth="1" />
      <circle cx="44" cy="22" r="6" fill="#ffbd2e" stroke="#dea123" strokeWidth="1" />
      <circle cx="64" cy="22" r="6" fill="#27c93f" stroke="#1aab29" strokeWidth="1" />
      
      {/* Terminal Content */}
      <text x="28" y="96" fill="var(--accent-blue)" fontSize="20" fontFamily="monospace" fontWeight="bold">~❯</text>
      <text x="56" y="96" fill="var(--text-foreground)" fontSize="20" fontFamily="monospace" clipPath="url(#cmd-clip)">kanbus list</text>
      
      <text x="28" y="140" fill="var(--text-muted)" fontSize="18" fontFamily="monospace" opacity="0">
        ID      STATUS    TITLE
        <animate attributeName="opacity" values="0; 1; 1; 0" dur="6s" keyTimes="0; 0.151; 0.98; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>
      <text x="28" y="172" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-1   open      Update docs
        <animate attributeName="opacity" values="0; 1; 1; 0" dur="6s" keyTimes="0; 0.152; 0.98; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>
      <text x="28" y="204" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-2   progress  Fix login flow
        <animate attributeName="opacity" values="0; 1; 1; 0" dur="6s" keyTimes="0; 0.153; 0.98; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>
      <text x="28" y="236" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-3   done      Add tests
        <animate attributeName="opacity" values="0; 1; 1; 0" dur="6s" keyTimes="0; 0.154; 0.98; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>
      
      {/* Typing cursor for command */}
      <line x1="56" y1="78" x2="56" y2="100" stroke="var(--accent-blue)" strokeWidth="10">
        <animate attributeName="x1" values="56; 190; 190; 56" dur="6s" keyTimes="0; 0.15; 0.98; 1" repeatCount="indefinite" />
        <animate attributeName="x2" values="56; 190; 190; 56" dur="6s" keyTimes="0; 0.15; 0.98; 1" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0;1;0" dur="0.8s" repeatCount="indefinite" />
        <animate attributeName="display" values="inline; inline; none; none" dur="6s" keyTimes="0; 0.145; 0.15; 1" repeatCount="indefinite" />
      </line>

      {/* Typing cursor for next prompt */}
      <g opacity="0">
        <animate attributeName="opacity" values="0; 0; 1; 1; 0" dur="6s" keyTimes="0; 0.155; 0.16; 0.98; 1" repeatCount="indefinite" />
        <text x="28" y="278" fill="var(--accent-blue)" fontSize="20" fontFamily="monospace" fontWeight="bold">~❯</text>
        <line x1="56" y1="260" x2="56" y2="284" stroke="var(--accent-blue)" strokeWidth="10">
          <animate attributeName="opacity" values="1;0;1;0" dur="0.8s" repeatCount="indefinite" />
        </line>
      </g>
    </g>
  );

  const renderKanbanBoard = () => (
    <g transform="scale(1) translate(0, 0)">
      {/* Board Base */}
      <rect x="0" y="0" width="500" height="300" fill="var(--column)" rx="10" />
      
      {/* Columns */}
      <rect x="20" y="20" width="140" height="260" fill="var(--background)" rx="8" />
      <rect x="180" y="20" width="140" height="260" fill="var(--background)" rx="8" />
      <rect x="340" y="20" width="140" height="260" fill="var(--background)" rx="8" />
      
      {/* Cards */}
      <rect x="30" y="35" width="120" height="48" fill="var(--card)" rx="6" />
      
      {/* Right Column Card - shifts down */}
      <motion.g
        animate={{ y: [0, 0, 63, 63, 0, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", times: [0, 0.5, 0.53, 0.9, 0.95, 1] }}
      >
        <rect x="350" y="35" width="120" height="48" fill="var(--card)" rx="6" />
      </motion.g>
      
      {/* Animated Card - moving between columns */}
      <motion.g
        animate={{ x: [0, 0, 160, 160, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", times: [0, 0.51, 0.54, 0.9, 0.95, 1] }}
      >
        <rect x="190" y="35" width="120" height="48" fill="var(--accent-blue)" rx="6" />
      </motion.g>

      {/* Animated Card - new item appearing */}
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 0, 1, 1, 0, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", times: [0, 0.05, 0.1, 0.9, 0.95, 1] }}
      >
        <rect x="30" y="98" width="120" height="48" fill="var(--accent-blue)" rx="6" />
      </motion.g>
    </g>
  );

  const renderJiraSync = () => (
    <g transform="scale(1.2) translate(-40, -25)">
      {/* Pull Line */}
      <line x1="100" y1="50" x2="100" y2="220" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="4 4" />
      <path d="M 95 215 L 100 220 L 105 215" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <text x="90" y="135" transform="rotate(-90 90 135)" textAnchor="middle" fill="var(--accent-blue)" fontSize="12" fontFamily="monospace" fontWeight="bold" letterSpacing="2">PULL</text>

      {/* Kanbus Board (Bottom) */}
      <Board y="180" opacity={1} />

      
      {/* Jira Node (Top) */}
      <g transform="translate(250, 90) scale(1, 0.5) rotate(45) translate(-100, -75)">
        <rect width="200" height="150" fill="var(--column)" rx="8" />
        
        {/* Bookmark on Green */}
        <rect x="40" y="25" width="40" height="40" fill="#22c55e" rx="6" />
        <svg x="48" y="33" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
        </svg>

        {/* Zap on Magenta */}
        <rect x="120" y="25" width="40" height="40" fill="#d946ef" rx="6" />
        <svg x="128" y="33" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>
        </svg>

        {/* Check on Blue */}
        <rect x="40" y="85" width="40" height="40" fill="#3b82f6" rx="6" />
        <svg x="48" y="93" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6 9 17l-5-5"/>
        </svg>

        {/* Dot on Red */}
        <rect x="120" y="85" width="40" height="40" fill="#ef4444" rx="6" />
        <svg x="128" y="93" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" fill="#ffffff" />
        </svg>
      </g>
    </g>
  );

  const renderLocalTasks = () => (
    <g transform="scale(1.2) translate(-40, -25)">
      {/* Local Board (Dashed/Transparent) */}
      <g transform={`translate(200, 200) scale(1, 0.5) rotate(45) translate(-100, -75)`} opacity={0.6}>
        <rect width="200" height="150" fill="transparent" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="4 4" rx="8" />
        <rect x="10" y="10" width="54" height="130" fill="var(--background)" rx="4" />
        <rect x="73" y="10" width="54" height="130" fill="var(--background)" rx="4" />
        <rect x="136" y="10" width="54" height="130" fill="var(--background)" rx="4" />
        <rect x="15" y="15" width="44" height="20" fill="var(--card)" rx="2" />
      </g>
      
      {/* Shared Board */}
      <Board x={300} y={100} />
      <g transform="translate(300, 100) scale(1, 0.5) rotate(45) translate(-100, -75)">
        <rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" />
      </g>

      {/* Promotion Arrow */}
      <path d="M 200 200 L 300 100" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="4 4">
        <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
      </path>

      <motion.g
        animate={{ x: [200, 300], y: [200, 100] }}
        transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
      >
        <g transform="scale(1, 0.5) rotate(45)">
          <rect width="44" height="20" fill="var(--accent-blue)" rx="2" />
        </g>
      </motion.g>
    </g>
  );

  const renderBeadsCompatibility = () => (
    <g transform="scale(1) translate(0, 0)">
      <defs>
        <clipPath id="cmd-clip-beads">
          <rect x="56" y="70" width="0" height="40">
            <animate attributeName="width" values="0; 120; 120; 0; 0; 135; 135; 0; 0" dur="12s" keyTimes="0; 0.15; 0.4; 0.401; 0.5; 0.65; 0.9; 0.901; 1" repeatCount="indefinite" />
          </rect>
        </clipPath>
      </defs>

      {/* Terminal Window Flat */}
      <rect x="0" y="0" width="500" height="300" fill="var(--column)" rx="10" />
      
      {/* Terminal Header */}
      <rect x="0" y="0" width="500" height="40" fill="var(--background)" rx="10" />
      
      {/* MacOS Window Buttons */}
      <circle cx="24" cy="22" r="6" fill="#ff5f56" />
      <circle cx="44" cy="22" r="6" fill="#ffbd2e" />
      <circle cx="64" cy="22" r="6" fill="#27c93f" />
      
      {/* Terminal Content */}
      <text x="28" y="96" fill="var(--accent-blue)" fontSize="20" fontFamily="monospace" fontWeight="bold">
        ~❯
        <animate attributeName="opacity" values="1; 1; 1; 0; 1; 1; 1; 0; 1" dur="12s" keyTimes="0; 0.15; 0.4; 0.401; 0.5; 0.65; 0.9; 0.901; 1" repeatCount="indefinite" />
      </text>
      
      {/* Command Text */}
      <g clipPath="url(#cmd-clip-beads)">
        <text x="56" y="96" fill="var(--text-foreground)" fontSize="20" fontFamily="monospace">
          beads list
          <animate attributeName="opacity" values="1; 1; 1; 0; 0; 0; 0; 0; 0" dur="12s" keyTimes="0; 0.15; 0.4; 0.401; 0.5; 0.65; 0.9; 0.901; 1" repeatCount="indefinite" />
        </text>
        <text x="56" y="96" fill="var(--text-foreground)" fontSize="20" fontFamily="monospace" opacity="0">
          kanbus list
          <animate attributeName="opacity" values="0; 0; 0; 0; 1; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.15; 0.4; 0.401; 0.5; 0.65; 0.9; 0.901; 1" repeatCount="indefinite" />
        </text>
      </g>
      
      <text x="28" y="140" fill="var(--text-muted)" fontSize="18" fontFamily="monospace" opacity="0">
        ID      STATUS    TITLE
        <animate attributeName="opacity" values="0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.151; 0.4; 0.401; 0.5; 0.651; 0.9; 0.901; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>
      <text x="28" y="172" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-1   open      Update docs
        <animate attributeName="opacity" values="0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.152; 0.4; 0.401; 0.5; 0.652; 0.9; 0.901; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>
      <text x="28" y="204" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-2   progress  Fix login flow
        <animate attributeName="opacity" values="0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.153; 0.4; 0.401; 0.5; 0.653; 0.9; 0.901; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>
      <text x="28" y="236" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-3   done      Add tests
        <animate attributeName="opacity" values="0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.154; 0.4; 0.401; 0.5; 0.654; 0.9; 0.901; 1" calcMode="discrete" repeatCount="indefinite" />
      </text>

      {/* Typing cursor for command */}
      <line x1="56" y1="78" x2="56" y2="100" stroke="var(--accent-blue)" strokeWidth="10">
        <animate attributeName="x1" values="56; 176; 176; 56; 56; 188; 188; 56; 56" dur="12s" keyTimes="0; 0.15; 0.4; 0.401; 0.5; 0.65; 0.9; 0.901; 1" repeatCount="indefinite" />
        <animate attributeName="x2" values="56; 176; 176; 56; 56; 188; 188; 56; 56" dur="12s" keyTimes="0; 0.15; 0.4; 0.401; 0.5; 0.65; 0.9; 0.901; 1" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0;1;0" dur="0.8s" repeatCount="indefinite" />
        <animate attributeName="display" values="inline; none; none; none; inline; none; none; none; none" dur="12s" keyTimes="0; 0.15; 0.4; 0.401; 0.5; 0.65; 0.9; 0.901; 1" calcMode="discrete" repeatCount="indefinite" />
      </line>

      {/* Typing cursor for next prompt */}
      <g opacity="0">
        <animate attributeName="opacity" values="0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.16; 0.4; 0.401; 0.5; 0.66; 0.9; 0.901; 1" calcMode="discrete" repeatCount="indefinite" />
        <text x="28" y="278" fill="var(--accent-blue)" fontSize="20" fontFamily="monospace" fontWeight="bold">~❯</text>
        <line x1="56" y1="260" x2="56" y2="284" stroke="var(--accent-blue)" strokeWidth="10">
          <animate attributeName="opacity" values="1;0;1;0" dur="0.8s" repeatCount="indefinite" />
        </line>
      </g>
    </g>
  );

  const renderVirtualProjects = () => {
    const FlatBoard = ({ x, y, width, height, opacity = 1, color = "var(--column)" }: { x: number, y: number, width: number, height: number, opacity?: number, color?: string }) => {
      const colWidth = width * 0.28;
      const colGap = width * 0.04;
      const colHeight = height * 0.85;
      const colY = height * 0.075;
      return (
        <g transform={`translate(${x}, ${y})`} opacity={opacity}>
          <rect width={width} height={height} fill={color} rx="6" />
          <rect x={colGap} y={colY} width={colWidth} height={colHeight} fill="var(--background)" rx="4" />
          <rect x={colGap * 2 + colWidth} y={colY} width={colWidth} height={colHeight} fill="var(--background)" rx="4" />
          <rect x={colGap * 3 + colWidth * 2} y={colY} width={colWidth} height={colHeight} fill="var(--background)" rx="4" />
        </g>
      );
    };

    return (
      <g>
        {/* Incoming Boards (Top Left and Top Right) */}
        <FlatBoard x={60} y={30} width={160} height={100} opacity={0.6} color="var(--card-muted)" />
        <FlatBoard x={280} y={30} width={160} height={100} opacity={0.6} color="var(--card-muted)" />

        {/* Unified Board (Bottom Center) */}
        <FlatBoard x={170} y={170} width={160} height={100} opacity={1} />

        {/* Connection Arrows */}
        <path d="M 140 100 L 170 220" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </path>
        <path d="M 162 210 L 170 220 L 160 215" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        
        <path d="M 360 100 L 330 220" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </path>
        <path d="M 340 215 L 330 220 L 338 210" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        
        {/* Animated incoming cards */}
        <motion.g
          animate={{ x: [140, 170], y: [100, 220], opacity: [0, 1, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
        >
          <rect width="30" height="12" fill="var(--accent-blue)" rx="2" transform="translate(-15, -6)" />
        </motion.g>

        <motion.g
          animate={{ x: [360, 330], y: [100, 220], opacity: [0, 1, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: "linear", delay: 1 }}
        >
          <rect width="30" height="12" fill="var(--accent-blue)" rx="2" transform="translate(-15, -6)" />
        </motion.g>
      </g>
    );
  };

  const renderVsCodePlugin = () => (
    <g transform="scale(1) translate(0, 0)">
      <defs>
        <clipPath id="vscode-clip">
          <rect x="0" y="0" width="500" height="300" rx="10" />
        </clipPath>
        <clipPath id="editor-clip">
          <rect x="0" y="0" width="250" height="300" />
        </clipPath>
      </defs>

      <g clipPath="url(#vscode-clip)">
        {/* Editor Pane (Left Half) */}
        <rect x="0" y="0" width="250" height="300" fill="var(--background)" />
        
        {/* Editor Content */}
        <g transform="translate(10, 20)" clipPath="url(#editor-clip)">
          {/* Line numbers */}
          <g fill="var(--text-muted)" fontSize="14" fontFamily="monospace" opacity="0.5">
            <text x="10" y="20">1</text>
            <text x="10" y="45">2</text>
            <text x="10" y="70">3</text>
            <text x="10" y="95">4</text>
            <text x="10" y="120">5</text>
            <text x="10" y="145">6</text>
            <text x="10" y="170">7</text>
            <text x="10" y="195">8</text>
            <text x="10" y="220">9</text>
          </g>
          
          {/* Code */}
          <g fontSize="14" fontFamily="monospace">
            <text x="35" y="20" fill="var(--accent-blue)">function <tspan fill="var(--text-foreground)">agentTask</tspan>() {'{'}</text>
            <text x="50" y="45" fill="var(--text-muted)">// sync issue</text>
            <text x="50" y="70" fill="var(--text-foreground)">const issue = board.get(<tspan fill="var(--accent-blue)">'T-1'</tspan>);</text>
            <text x="50" y="95" fill="var(--text-foreground)">if (issue.isReady) {'{'}</text>
            <text x="65" y="120" fill="var(--text-foreground)">issue.status = <tspan fill="var(--accent-blue)">'in_progress'</tspan>;</text>
            <text x="65" y="145" fill="var(--text-foreground)">board.update(issue);</text>
            <text x="50" y="170" fill="var(--text-foreground)">{'}'}</text>
            <text x="35" y="195" fill="var(--text-foreground)">{'}'}</text>
          </g>

          {/* Typing Cursor */}
          <line x1="215" y1="133" x2="215" y2="148" stroke="var(--accent-blue)" strokeWidth="2">
            <animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite" />
          </line>
        </g>

        {/* Kanban Pane (Right Half) Background */}
        <rect x="250" y="0" width="250" height="300" fill="var(--column)" />
        
        {/* Separator */}
        <line x1="250" y1="0" x2="250" y2="300" stroke="var(--border)" strokeWidth="2" />

        {/* Kanban Pane */}
        <g transform="translate(250, 0)">
          {/* Columns */}
          <rect x="10" y="20" width="70" height="260" fill="var(--background)" rx="6" />
          <rect x="90" y="20" width="70" height="260" fill="var(--background)" rx="6" />
          <rect x="170" y="20" width="70" height="260" fill="var(--background)" rx="6" />
          
          {/* Cards */}
          <rect x="15" y="35" width="60" height="24" fill="var(--card)" rx="3" />
          
          {/* Right Column Card - shifts down */}
          <motion.g
            animate={{ y: [0, 0, 32, 32, 0, 0] }}
            transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", times: [0, 0.5, 0.53, 0.9, 0.95, 1] }}
          >
            <rect x="175" y="35" width="60" height="24" fill="var(--card)" rx="3" />
          </motion.g>
          
          {/* Animated Card - moving between columns (middle to right) */}
          <motion.g
            animate={{ x: [0, 0, 80, 80, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
            transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", times: [0, 0.51, 0.54, 0.9, 0.95, 1] }}
          >
            <rect x="95" y="35" width="60" height="24" fill="var(--accent-blue)" rx="3" />
          </motion.g>

          {/* Animated Card - new item appearing */}
          <motion.g
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0, 1, 1, 0, 0] }}
            transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", times: [0, 0.05, 0.1, 0.9, 0.95, 1] }}
          >
            <rect x="15" y="67" width="60" height="24" fill="var(--accent-blue)" rx="3" />
          </motion.g>
        </g>
      </g>
    </g>
  );

  const renderIntegratedWiki = () => (
    <g transform="scale(1) translate(0, 0)">
      <defs>
        <clipPath id="wiki-clip">
          <rect x="0" y="0" width="500" height="300" rx="10" />
        </clipPath>
        
        {/* Tiny5 font import for the wiki text */}
        <style>
          {`
            @import url('https://fonts.googleapis.com/css2?family=Tiny5&display=swap');
            .tiny-text { font-family: 'Tiny5', monospace; font-size: 8px; }
          `}
        </style>
      </defs>

      <g clipPath="url(#wiki-clip)">
        {/* Full Kanban Board Base */}
        <motion.rect 
          x="0" y="0" height="300" fill="var(--column)" 
          animate={{ width: [500, 300, 300, 500] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", times: [0, 0.2, 0.8, 1] }}
        />
        
        {/* Animated Kanban Content (Squishing to the left) */}
        <motion.g
          animate={{ scaleX: [1, 0.56, 0.56, 1] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", times: [0, 0.2, 0.8, 1] }}
          style={{ originX: 0 }}
        >
          {/* Columns */}
          <rect x="20" y="20" width="140" height="260" fill="var(--background)" rx="8" />
          <rect x="180" y="20" width="140" height="260" fill="var(--background)" rx="8" />
          <rect x="340" y="20" width="140" height="260" fill="var(--background)" rx="8" />
          
          {/* Cards */}
          <rect x="30" y="35" width="120" height="32" fill="var(--card)" rx="6" />
          <rect x="30" y="77" width="120" height="32" fill="var(--card)" rx="6" />
          <rect x="30" y="119" width="120" height="32" fill="var(--card)" rx="6" />
          <rect x="30" y="161" width="120" height="32" fill="var(--card)" rx="6" />
          
          <rect x="190" y="35" width="120" height="32" fill="var(--card)" rx="6" />
          <rect x="190" y="77" width="120" height="32" fill="var(--card)" rx="6" />
          <rect x="190" y="119" width="120" height="32" fill="var(--accent-blue)" rx="6" />
          
          <rect x="350" y="35" width="120" height="32" fill="var(--card)" rx="6" />
          <rect x="350" y="77" width="120" height="32" fill="var(--card)" rx="6" />
        </motion.g>

        {/* Sliding Wiki Panel */}
        <motion.g
          animate={{ x: [500, 300, 300, 500] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", times: [0, 0.2, 0.8, 1] }}
        >
          {/* Panel Shadow / Border */}
          <line x1="0" y1="0" x2="0" y2="300" stroke="var(--border)" strokeWidth="2" />
          <rect x="0" y="0" width="200" height="300" fill="var(--background)" />
          
          {/* Wiki Content */}
          <g transform="translate(15, 25)" className="tiny-text" fill="var(--text-muted)">
            <text x="0" y="0" fill="var(--text-foreground)" fontSize="12">Project Architecture</text>
            <rect x="0" y="8" width="170" height="1" fill="var(--border)" />
            
            <text x="0" y="25">The core system consists of several</text>
            <text x="0" y="35">microservices that communicate via</text>
            <text x="0" y="45"><tspan fill="var(--accent-blue)">event streams</tspan>. This allows us to scale</text>
            <text x="0" y="55">independently.</text>
            
            <text x="0" y="75" fill="var(--text-foreground)">1. Authentication Flow</text>
            <text x="0" y="85">User tokens are issued by the</text>
            <text x="0" y="95"><tspan fill="var(--accent-blue)">Auth Gateway</tspan> and verified by</text>
            <text x="0" y="105">edge nodes before routing.</text>
            
            <text x="0" y="125" fill="var(--text-foreground)">2. Data Storage</text>
            <text x="0" y="135">We use a combination of relational</text>
            <text x="0" y="145">databases and document stores.</text>
            <text x="0" y="155">See <tspan fill="var(--accent-blue)">Schema Definitions</tspan> for details.</text>
            
            <text x="0" y="175" fill="var(--text-foreground)">Deployment</text>
            <text x="0" y="185">All services are containerized</text>
            <text x="0" y="195">and orchestrated using</text>
            <text x="0" y="205"><tspan fill="var(--accent-blue)">Kubernetes clusters</tspan>.</text>
            
            {/* Some fake code blocks */}
            <rect x="0" y="220" width="160" height="35" fill="var(--card)" rx="2" />
            <text x="5" y="232" fill="var(--accent-blue)">docker build -t app .</text>
            <text x="5" y="244" fill="var(--accent-blue)">kubectl apply -f k8s/</text>
          </g>
        </motion.g>
      </g>
    </g>
  );

  const renderPolicyAsCode = () => {
    const PolicyItem = ({ y, text, index }: { y: number, text: string, index: number }) => {
      const checkTime = (index + 1) * 1; 
      const t1 = checkTime / 8;
      const t2 = (checkTime + 0.3) / 8;
      const t3 = 7.0 / 8;
      const t4 = 7.3 / 8;
      
      return (
        <g transform={`translate(20, ${y})`}>
          <motion.g
            animate={{ opacity: [1, 1, 0, 0, 1, 1] }}
            transition={{ duration: 8, repeat: Infinity, times: [0, t1, t2, t3, t4, 1], ease: "easeInOut" }}
          >
            {/* Lucide square */}
            <rect width="18" height="18" x="3" y="3" rx="2" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </motion.g>
          <motion.g
            animate={{ opacity: [0, 0, 1, 1, 0, 0] }}
            transition={{ duration: 8, repeat: Infinity, times: [0, t1, t2, t3, t4, 1], ease: "easeInOut" }}
          >
            {/* Lucide square-check-big */}
            <path d="M21 10.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12.5" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="m9 11 3 3L22 4" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </motion.g>
          <text x="35" y="16" fill="var(--text-muted)" fontSize="16" className="tiny-text" fontFamily="'Tiny5', monospace">{text}</text>
        </g>
      );
    };

    return (
      <g transform="scale(1) translate(0, 0)">
        <defs>
          <style>
            {`
              @import url('https://fonts.googleapis.com/css2?family=Tiny5&display=swap');
              .tiny-text { font-family: 'Tiny5', monospace; }
            `}
          </style>
        </defs>
        
        <rect x="0" y="0" width="500" height="300" fill="var(--column)" rx="10" />
        <rect x="0" y="0" width="500" height="40" fill="var(--background)" rx="10" />
        <text x="20" y="25" fill="var(--text-foreground)" fontSize="16" fontFamily="monospace">workflow.policy</text>
        
        <g transform="translate(20, 60)">
          <PolicyItem y={0} text="Epic cannot transition to ready without at least 3 tasks" index={0} />
          <PolicyItem y={45} text="PRs cannot be merged without passing CI tests" index={1} />
          <PolicyItem y={90} text="Tasks in 'In Progress' must have an assignee" index={2} />
          <PolicyItem y={135} text="Design tasks require a valid Figma link attached" index={3} />
          <PolicyItem y={180} text="Bugs require clear steps to reproduce in description" index={4} />
        </g>
      </g>
    );
  };

  const renders: Record<string, () => React.ReactNode> = {
    "core-management": renderCli,
    "kanban-board": renderKanbanBoard,
    "jira-sync": renderJiraSync,
    "local-tasks": renderLocalTasks,
    "beads-compatibility": renderBeadsCompatibility,
    "virtual-projects": renderVirtualProjects,
    "vscode-plugin": renderVsCodePlugin,
    "integrated-wiki": renderIntegratedWiki,
    "policy-as-code": renderPolicyAsCode,
  };

  const renderContent = renders[type] || renderCli;

  return (
    <div className={`w-full aspect-[5/3] flex flex-col items-center justify-center overflow-hidden relative pictogram ${className || ""}`} style={{ ...style }}>
      {/* Background glow to ground the 3D window */}
      <div 
        className="absolute top-[60%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] rounded-[100%] pointer-events-none z-0"
        style={{
          background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
        }}
      />
      <svg width="100%" height="100%" viewBox="0 0 500 300" fill="none" xmlns="http://www.w3.org/2000/svg" className="z-10 absolute inset-0 m-auto" preserveAspectRatio={type === "core-management" || type === "kanban-board" || type === "beads-compatibility" || type === "vscode-plugin" || type === "integrated-wiki" || type === "policy-as-code" ? "none" : "xMidYMid meet"}>
        <defs>
          <radialGradient id="feature-glow" cx="50%" cy="50%" r="50%" fx="50%" fy="50%">
            <stop offset="0%" stopColor="var(--glow-center)" />
            <stop offset="100%" stopColor="var(--glow-edge)" />
          </radialGradient>
        </defs>
        
        {/* Ambient background glow / shadow */}
        {type !== "core-management" && type !== "kanban-board" && type !== "beads-compatibility" && type !== "vscode-plugin" && type !== "integrated-wiki" && type !== "policy-as-code" && (
          <ellipse cx="250" cy="150" rx="200" ry="140" fill="url(#feature-glow)" />
        )}
        
        {renderContent()}
      </svg>
    </div>
  );
}
