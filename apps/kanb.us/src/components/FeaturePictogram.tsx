import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";

export type FeaturePictogramType = 
  | "core-management" 
  | "kanban-board" 
  | "realtime-collaboration"
  | "jira-sync" 
  | "local-tasks" 
  | "beads-compatibility" 
  | "virtual-projects" 
  | "vscode-plugin" 
  | "integrated-wiki" 
  | "policy-as-code"
  | "agile-metrics"
  | "git-native-storage";

export function FeaturePictogram({ type, style, className }: { type: string, style?: React.CSSProperties, className?: string }) {
  const prefersReducedMotion = useReducedMotion();
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
            <animate attributeName="width" values="0; 0; 12; 12; 25; 25; 37; 37; 49; 49; 61; 61; 74; 74; 86; 86; 98; 98; 110; 110; 123; 123; 135; 135; 0; 0" dur="6s" keyTimes="0; 0.060; 0.061; 0.073; 0.074; 0.086; 0.087; 0.099; 0.100; 0.112; 0.113; 0.125; 0.126; 0.140; 0.141; 0.153; 0.154; 0.166; 0.167; 0.179; 0.180; 0.192; 0.193; 0.970; 0.971; 1" repeatCount="indefinite" />
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
      <g clipPath="url(#cmd-clip)">
        <text x="56" y="96" fill="var(--text-foreground)" fontSize="20" fontFamily="monospace">kanbus list</text>
      </g>
      
      <text x="28" y="140" fill="var(--text-muted)" fontSize="18" fontFamily="monospace" opacity="0">
        ID      STATUS    TITLE
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0" dur="6s" keyTimes="0; 0.200; 0.201; 0.969; 0.970; 1" repeatCount="indefinite" />
      </text>
      <text x="28" y="172" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-1   open      Update docs
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0" dur="6s" keyTimes="0; 0.201; 0.202; 0.969; 0.970; 1" repeatCount="indefinite" />
      </text>
      <text x="28" y="204" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-2   progress  Fix login flow
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0" dur="6s" keyTimes="0; 0.202; 0.203; 0.969; 0.970; 1" repeatCount="indefinite" />
      </text>
      <text x="28" y="236" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-3   done      Add tests
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0" dur="6s" keyTimes="0; 0.203; 0.204; 0.969; 0.970; 1" repeatCount="indefinite" />
      </text>
      
      {/* Typing cursor for command */}
      <line x1="56" y1="78" x2="56" y2="100" stroke="var(--accent-blue)" strokeWidth="10">
        <animate attributeName="x1" values="56; 56; 68; 68; 81; 81; 93; 93; 105; 105; 117; 117; 130; 130; 142; 142; 154; 154; 166; 166; 179; 179; 190; 190; 56; 56" dur="6s" keyTimes="0; 0.060; 0.061; 0.073; 0.074; 0.086; 0.087; 0.099; 0.100; 0.112; 0.113; 0.125; 0.126; 0.140; 0.141; 0.153; 0.154; 0.166; 0.167; 0.179; 0.180; 0.192; 0.193; 0.970; 0.971; 1" repeatCount="indefinite" />
        <animate attributeName="x2" values="56; 56; 68; 68; 81; 81; 93; 93; 105; 105; 117; 117; 130; 130; 142; 142; 154; 154; 166; 166; 179; 179; 190; 190; 56; 56" dur="6s" keyTimes="0; 0.060; 0.061; 0.073; 0.074; 0.086; 0.087; 0.099; 0.100; 0.112; 0.113; 0.125; 0.126; 0.140; 0.141; 0.153; 0.154; 0.166; 0.167; 0.179; 0.180; 0.192; 0.193; 0.970; 0.971; 1" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0;1;0" dur="0.8s" repeatCount="indefinite" />
        <animate attributeName="display" values="inline; inline; none; none" dur="6s" keyTimes="0; 0.195; 0.20; 1" repeatCount="indefinite" />
      </line>

      {/* Typing cursor for next prompt */}
      <g opacity="0">
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0" dur="6s" keyTimes="0; 0.209; 0.210; 0.969; 0.970; 1" repeatCount="indefinite" />
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

  const renderRealtimeCollaboration = () => (
    <g transform="scale(1) translate(0, 0)">
      {/* Gossip lines (behind everything) */}
      <path
        d="M 105 140 L 250 140"
        fill="none"
        stroke="var(--accent-blue)"
        strokeWidth="2.5"
        strokeDasharray="7 7"
        opacity="0.85"
      >
        <animate attributeName="stroke-dashoffset" from="14" to="0" dur="1s" repeatCount="indefinite" />
      </path>
      <path
        d="M 250 140 L 395 140"
        fill="none"
        stroke="var(--accent-blue)"
        strokeWidth="2.5"
        strokeDasharray="7 7"
        opacity="0.85"
      >
        <animate attributeName="stroke-dashoffset" from="14" to="0" dur="1s" repeatCount="indefinite" />
      </path>

      {/* Pulses */}
      <motion.circle
        r="5"
        fill="var(--accent-blue)"
        animate={{ cx: [105, 250], opacity: [0, 1, 1, 0] }}
        transition={{ duration: 2.6, repeat: Infinity, ease: "linear" }}
        cy={140}
      />
      <motion.circle
        r="5"
        fill="var(--accent-blue)"
        animate={{ cx: [250, 395], opacity: [0, 1, 1, 0] }}
        transition={{ duration: 2.6, repeat: Infinity, ease: "linear", delay: 0.9 }}
        cy={140}
      />

      {/* Left: CLI / mutator */}
      <g transform="translate(30, 80)">
        <rect width="150" height="120" fill="var(--card)" rx="10" stroke="var(--border)" strokeWidth="2" />
        <rect width="150" height="26" fill="var(--background)" rx="10" />
        <circle cx="18" cy="13" r="5" fill="#ff5f56" opacity="0.85" />
        <circle cx="36" cy="13" r="5" fill="#ffbd2e" opacity="0.85" />
        <circle cx="54" cy="13" r="5" fill="#27c93f" opacity="0.85" />
        <text x="16" y="56" fill="var(--accent-blue)" fontSize="14" fontFamily="monospace" fontWeight="800">~❯</text>
        <text x="44" y="56" fill="var(--text-foreground)" fontSize="14" fontFamily="monospace">kbs update</text>
        <rect x="16" y="70" width="118" height="10" fill="var(--card-muted)" rx="5" opacity="0.9" />
        <rect x="16" y="88" width="92" height="10" fill="var(--card-muted)" rx="5" opacity="0.75" />
        <rect x="16" y="106" width="104" height="10" fill="var(--card-muted)" rx="5" opacity="0.6" />
      </g>

      {/* Right: watcher + overlay */}
      <g opacity="0.8">
        <rect x="320" y="80" width="150" height="120" fill="transparent" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="6 6" rx="10">
          <animate attributeName="stroke-dashoffset" from="12" to="0" dur="1.4s" repeatCount="indefinite" />
        </rect>
      </g>
      <g transform="translate(320, 80)">
        <rect width="150" height="120" fill="var(--card)" rx="10" stroke="var(--border)" strokeWidth="2" />
        <rect x="12" y="14" width="40" height="92" fill="var(--background)" rx="6" />
        <rect x="55" y="14" width="40" height="92" fill="var(--background)" rx="6" />
        <rect x="98" y="14" width="40" height="92" fill="var(--background)" rx="6" />
        <rect x="18" y="24" width="28" height="16" fill="var(--card-muted)" rx="4" />
        <rect x="61" y="24" width="28" height="16" rx="4" fill="var(--accent-blue)">
          <animate attributeName="x" values="61; 104; 61" dur="6s" repeatCount="indefinite" calcMode="spline" keySplines="0.42 0 0.58 1; 0.42 0 0.58 1" />
        </rect>
        <rect x="18" y="48" width="28" height="16" fill="var(--card-muted)" rx="4" opacity="0.8" />
      </g>

      {/* Center: broker */}
      <g>
        <circle cx="250" cy="140" r="28" fill="var(--background)" stroke="var(--accent-blue)" strokeWidth="3" />
        <circle cx="250" cy="140" r="16" fill="var(--card)" stroke="var(--border)" strokeWidth="2" opacity="0.95" />
        <text x="250" y="146" textAnchor="middle" fill="var(--text-foreground)" fontSize="11" fontFamily="monospace" fontWeight="800">
          BUS
        </text>
      </g>
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
            <animate attributeName="width" values="0; 0; 12; 12; 24; 24; 36; 36; 48; 48; 60; 60; 72; 72; 84; 84; 96; 96; 108; 108; 120; 120; 0; 0; 12; 12; 25; 25; 37; 37; 49; 49; 61; 61; 74; 74; 86; 86; 98; 98; 110; 110; 123; 123; 135; 135; 0; 0" dur="12s" keyTimes="0; 0.030; 0.031; 0.043; 0.044; 0.056; 0.057; 0.069; 0.070; 0.082; 0.083; 0.097; 0.098; 0.110; 0.111; 0.123; 0.124; 0.136; 0.137; 0.149; 0.150; 0.395; 0.396; 0.530; 0.531; 0.543; 0.544; 0.556; 0.557; 0.569; 0.570; 0.582; 0.583; 0.595; 0.596; 0.610; 0.611; 0.623; 0.624; 0.636; 0.637; 0.649; 0.650; 0.662; 0.663; 0.895; 0.896; 1" repeatCount="indefinite" />
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
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.180; 0.181; 0.394; 0.395; 0.680; 0.681; 0.894; 0.895; 1" repeatCount="indefinite" />
      </text>
      <text x="28" y="172" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-1   open      Update docs
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.181; 0.182; 0.394; 0.395; 0.681; 0.682; 0.894; 0.895; 1" repeatCount="indefinite" />
      </text>
      <text x="28" y="204" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-2   progress  Fix login flow
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.182; 0.183; 0.394; 0.395; 0.682; 0.683; 0.894; 0.895; 1" repeatCount="indefinite" />
      </text>
      <text x="28" y="236" fill="var(--text-foreground)" fontSize="18" fontFamily="monospace" opacity="0">
        tsk-3   done      Add tests
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.183; 0.184; 0.394; 0.395; 0.683; 0.684; 0.894; 0.895; 1" repeatCount="indefinite" />
      </text>

      {/* Typing cursor for command */}
      <line x1="56" y1="78" x2="56" y2="100" stroke="var(--accent-blue)" strokeWidth="10">
        <animate attributeName="x1" values="56; 56; 68; 68; 80; 80; 92; 92; 104; 104; 116; 116; 128; 128; 140; 140; 152; 152; 164; 164; 176; 176; 56; 56; 68; 68; 80; 80; 92; 92; 104; 104; 116; 116; 128; 128; 140; 140; 152; 152; 164; 164; 176; 176; 188; 188; 56; 56" dur="12s" keyTimes="0; 0.030; 0.031; 0.043; 0.044; 0.056; 0.057; 0.069; 0.070; 0.082; 0.083; 0.097; 0.098; 0.110; 0.111; 0.123; 0.124; 0.136; 0.137; 0.149; 0.150; 0.395; 0.396; 0.530; 0.531; 0.543; 0.544; 0.556; 0.557; 0.569; 0.570; 0.582; 0.583; 0.595; 0.596; 0.610; 0.611; 0.623; 0.624; 0.636; 0.637; 0.649; 0.650; 0.662; 0.663; 0.895; 0.896; 1" repeatCount="indefinite" />
        <animate attributeName="x2" values="56; 56; 68; 68; 80; 80; 92; 92; 104; 104; 116; 116; 128; 128; 140; 140; 152; 152; 164; 164; 176; 176; 56; 56; 68; 68; 80; 80; 92; 92; 104; 104; 116; 116; 128; 128; 140; 140; 152; 152; 164; 164; 176; 176; 188; 188; 56; 56" dur="12s" keyTimes="0; 0.030; 0.031; 0.043; 0.044; 0.056; 0.057; 0.069; 0.070; 0.082; 0.083; 0.097; 0.098; 0.110; 0.111; 0.123; 0.124; 0.136; 0.137; 0.149; 0.150; 0.395; 0.396; 0.530; 0.531; 0.543; 0.544; 0.556; 0.557; 0.569; 0.570; 0.582; 0.583; 0.595; 0.596; 0.610; 0.611; 0.623; 0.624; 0.636; 0.637; 0.649; 0.650; 0.662; 0.663; 0.895; 0.896; 1" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0;1;0" dur="0.8s" repeatCount="indefinite" />
        <animate attributeName="display" values="inline; none; none; none; inline; none; none; none; none" dur="12s" keyTimes="0; 0.18; 0.4; 0.401; 0.5; 0.68; 0.9; 0.901; 1" calcMode="discrete" repeatCount="indefinite" />
      </line>

      {/* Typing cursor for next prompt */}
      <g opacity="0">
        <animate attributeName="opacity" values="0; 0; 1; 1; 0; 0; 1; 1; 0; 0" dur="12s" keyTimes="0; 0.189; 0.190; 0.394; 0.395; 0.689; 0.690; 0.894; 0.895; 1" repeatCount="indefinite" />
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
    const SignFace = ({ symbol }: { symbol: "arrow" | "warning" | "stop" }) => {
      if (symbol === "arrow") {
        return (
          <g>
            <rect x="-20" y="-20" width="40" height="40" rx="6" fill="#1f8ef1" />
            <path d="M-8 0h16M2-8l8 8-8 8" fill="none" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        );
      }
      if (symbol === "warning") {
        return (
          <g>
            <path d="M0-22 20 16 -20 16Z" fill="#f59e0b" />
            <path d="M0-9v12M0 9v0" fill="none" stroke="#111827" strokeWidth="3" strokeLinecap="round" />
          </g>
        );
      }
      return (
        <g>
          <polygon points="-18,-24 18,-24 30,-12 30,12 18,24 -18,24 -30,12 -30,-12" fill="#ef4444" />
          <rect x="-9" y="-2" width="18" height="4" rx="2" fill="#ffffff" />
        </g>
      );
    };

    const AnimatedSign = ({
      symbol,
      laneOffset,
      delay,
    }: {
      symbol: "arrow" | "warning" | "stop";
      laneOffset: number;
      delay: number;
    }) => (
      <motion.g
        initial={{ x: 250 + laneOffset * 0.35, y: 74, scale: 0.3, opacity: 0 }}
        animate={{
          x: [250 + laneOffset * 0.35, 250 + laneOffset * 0.7, 250 + laneOffset],
          y: [74, 150, 244],
          scale: [0.3, 0.7, 1.25],
          opacity: [0, 1, 0],
        }}
        transition={{ duration: 6.2, ease: "easeInOut", repeat: Infinity, delay }}
      >
        <rect x="-2" y="20" width="4" height="18" fill="var(--text-muted)" opacity={0.75} />
        <SignFace symbol={symbol} />
      </motion.g>
    );

    if (prefersReducedMotion) {
      return (
        <g transform="scale(1) translate(0, 0)">
          <defs>
            <linearGradient id="policy-gradient-static" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#0f172a" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="500" height="300" fill="url(#policy-gradient-static)" rx="10" />
          <path d="M150 290 250 90 350 290Z" fill="none" stroke="var(--text-muted)" strokeOpacity="0.25" strokeWidth="2" />
          <g transform="translate(210,170) scale(0.65)"><SignFace symbol="arrow" /></g>
          <g transform="translate(250,140) scale(0.85)"><SignFace symbol="warning" /></g>
          <g transform="translate(300,210) scale(1.05)"><SignFace symbol="stop" /></g>
        </g>
      );
    }

    return (
      <g transform="scale(1) translate(0, 0)">
        <defs>
          <linearGradient id="policy-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0f172a" />
            <stop offset="100%" stopColor="#1e293b" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="500" height="300" fill="url(#policy-gradient)" rx="10" />
        <path d="M130 300 250 72 370 300" fill="none" stroke="var(--text-muted)" strokeOpacity="0.22" strokeWidth="2" />
        <motion.path
          d="M250 78 250 294"
          stroke="var(--text-muted)"
          strokeOpacity="0.2"
          strokeWidth="2"
          strokeDasharray="8 12"
          animate={{ strokeDashoffset: [0, -40] }}
          transition={{ duration: 3.2, repeat: Infinity, ease: "linear" }}
        />
        <AnimatedSign symbol="arrow" laneOffset={-58} delay={0} />
        <AnimatedSign symbol="warning" laneOffset={0} delay={1.6} />
        <AnimatedSign symbol="stop" laneOffset={58} delay={3.2} />
      </g>
    );
  };

  const renderAgileMetrics = () => (
    <g transform="scale(1) translate(0, 0)">
      <rect x="0" y="0" width="500" height="300" fill="var(--column)" rx="10" />
      <rect x="24" y="20" width="148" height="120" fill="var(--card)" rx="10" />
      <rect x="188" y="20" width="288" height="120" fill="var(--card)" rx="10" />
      <rect x="24" y="156" width="452" height="124" fill="var(--card)" rx="10" />

      <text x="40" y="48" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">TOTAL ISSUES</text>
      <text x="40" y="96" fill="var(--text-foreground)" fontSize="34" fontWeight="700" fontFamily="monospace">124</text>

      <text x="204" y="48" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">STATUS</text>
      <g transform="translate(204, 62)">
        <rect x="0" y="0" width="220" height="12" rx="6" fill="var(--background)" />
        <rect x="0" y="0" width="90" height="12" rx="6" fill="var(--accent-blue)" />
        <rect x="90" y="0" width="72" height="12" rx="0" fill="var(--accent-yellow)" />
        <rect x="162" y="0" width="58" height="12" rx="6" fill="var(--accent-green)" />
      </g>

      <text x="40" y="182" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">ISSUES BY TYPE</text>
      <line x1="48" y1="264" x2="448" y2="264" stroke="var(--background)" strokeWidth="2" />
      <line x1="48" y1="176" x2="48" y2="264" stroke="var(--background)" strokeWidth="2" />

      <rect x="96" width="36" y="214" height="50" rx="4" fill="var(--accent-blue)" />
      <rect x="168" width="36" y="198" height="66" rx="4" fill="var(--accent-yellow)" />
      <rect x="240" width="36" y="184" height="80" rx="4" fill="var(--accent-green)" />
      <rect x="312" width="36" y="208" height="56" rx="4" fill="var(--accent-red)" />
      <rect x="384" width="36" y="220" height="44" rx="4" fill="var(--text-muted)" />
    </g>
  );

  const renderGitNativeStorage = () => (
    <g transform="scale(1) translate(0, 0)">
      {/* Git branch line */}
      <line x1="80" y1="40" x2="80" y2="270" stroke="var(--accent-blue)" strokeWidth="3" />

      {/* Commits on the branch */}
      <circle cx="80" cy="70" r="8" fill="var(--accent-blue)" />
      <circle cx="80" cy="130" r="8" fill="var(--accent-blue)" />
      <circle cx="80" cy="190" r="8" fill="var(--accent-blue)" />
      <motion.circle
        cx={80}
        cy={250}
        r={8}
        fill="var(--accent-blue)"
        animate={{ opacity: [0, 0, 1, 1, 0] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", times: [0, 0.3, 0.4, 0.9, 1] }}
      />

      {/* File tree from commits */}
      <g transform="translate(120, 50)">
        <text x="0" y="14" fill="var(--text-muted)" fontSize="13" fontFamily="monospace">project/</text>
        <line x1="8" y1="22" x2="8" y2="84" stroke="var(--border)" strokeWidth="1" />

        <line x1="8" y1="38" x2="20" y2="38" stroke="var(--border)" strokeWidth="1" />
        <text x="24" y="42" fill="var(--text-muted)" fontSize="13" fontFamily="monospace">issues/</text>
        <line x1="32" y1="50" x2="32" y2="84" stroke="var(--border)" strokeWidth="1" />

        <line x1="32" y1="62" x2="44" y2="62" stroke="var(--border)" strokeWidth="1" />
        <text x="48" y="66" fill="var(--text-foreground)" fontSize="13" fontFamily="monospace">tsk-1.json</text>

        <line x1="32" y1="84" x2="44" y2="84" stroke="var(--border)" strokeWidth="1" />
        <text x="48" y="88" fill="var(--text-foreground)" fontSize="13" fontFamily="monospace">tsk-2.json</text>
      </g>

      {/* Animated new file appearing */}
      <motion.g
        transform="translate(120, 50)"
        animate={{ opacity: [0, 0, 1, 1, 0] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", times: [0, 0.3, 0.4, 0.9, 1] }}
      >
        <line x1="32" y1="84" x2="32" y2="106" stroke="var(--border)" strokeWidth="1" />
        <line x1="32" y1="106" x2="44" y2="106" stroke="var(--border)" strokeWidth="1" />
        <text x="48" y="110" fill="var(--accent-blue)" fontSize="13" fontFamily="monospace">tsk-3.json</text>
      </motion.g>

      {/* JSON preview card */}
      <g transform="translate(290, 40)">
        <rect width="180" height="130" fill="var(--background)" rx="8" stroke="var(--border)" strokeWidth="1" />
        <text x="14" y="24" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">{'{'}</text>
        <text x="26" y="42" fill="var(--accent-blue)" fontSize="11" fontFamily="monospace">"id"</text>
        <text x="54" y="42" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">:</text>
        <text x="62" y="42" fill="var(--text-foreground)" fontSize="11" fontFamily="monospace">"tsk-1",</text>
        <text x="26" y="60" fill="var(--accent-blue)" fontSize="11" fontFamily="monospace">"title"</text>
        <text x="72" y="60" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">:</text>
        <text x="80" y="60" fill="var(--text-foreground)" fontSize="11" fontFamily="monospace">"Update docs",</text>
        <text x="26" y="78" fill="var(--accent-blue)" fontSize="11" fontFamily="monospace">"status"</text>
        <text x="80" y="78" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">:</text>
        <text x="88" y="78" fill="var(--text-foreground)" fontSize="11" fontFamily="monospace">"open",</text>
        <text x="26" y="96" fill="var(--accent-blue)" fontSize="11" fontFamily="monospace">"type"</text>
        <text x="62" y="96" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">:</text>
        <text x="70" y="96" fill="var(--text-foreground)" fontSize="11" fontFamily="monospace">"task"</text>
        <text x="14" y="114" fill="var(--text-muted)" fontSize="11" fontFamily="monospace">{'}'}</text>
      </g>

      {/* "No database" crossed-out icon */}
      <g transform="translate(310, 200)">
        <rect width="140" height="60" fill="var(--card)" rx="8" />
        <text x="70" y="24" textAnchor="middle" fill="var(--text-muted)" fontSize="12" fontFamily="monospace">No database.</text>
        <text x="70" y="44" textAnchor="middle" fill="var(--text-muted)" fontSize="12" fontFamily="monospace">Just files in Git.</text>
      </g>
    </g>
  );

  const renders: Record<string, () => React.ReactNode> = {
    "core-management": renderCli,
    "kanban-board": renderKanbanBoard,
    "realtime-collaboration": renderRealtimeCollaboration,
    "jira-sync": renderJiraSync,
    "local-tasks": renderLocalTasks,
    "beads-compatibility": renderBeadsCompatibility,
    "virtual-projects": renderVirtualProjects,
    "vscode-plugin": renderVsCodePlugin,
    "integrated-wiki": renderIntegratedWiki,
    "policy-as-code": renderPolicyAsCode,
    "agile-metrics": renderAgileMetrics,
    "git-native-storage": renderGitNativeStorage,
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
      <svg width="100%" height="100%" viewBox="0 0 500 300" fill="none" xmlns="http://www.w3.org/2000/svg" className="z-10 absolute inset-0 m-auto" preserveAspectRatio={type === "core-management" || type === "kanban-board" || type === "beads-compatibility" || type === "vscode-plugin" || type === "integrated-wiki" || type === "policy-as-code" || type === "agile-metrics" || type === "git-native-storage" ? "none" : "xMidYMid meet"}>
        <defs>
          <radialGradient id="feature-glow" cx="50%" cy="50%" r="50%" fx="50%" fy="50%">
            <stop offset="0%" stopColor="var(--glow-center)" />
            <stop offset="100%" stopColor="var(--glow-edge)" />
          </radialGradient>
        </defs>
        
        {/* Ambient background glow / shadow */}
        {type !== "core-management" && type !== "kanban-board" && type !== "beads-compatibility" && type !== "vscode-plugin" && type !== "integrated-wiki" && type !== "policy-as-code" && type !== "agile-metrics" && type !== "git-native-storage" && (
          <ellipse cx="250" cy="150" rx="200" ry="140" fill="url(#feature-glow)" />
        )}
        
        {renderContent()}
      </svg>
    </div>
  );
}
