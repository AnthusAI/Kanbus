import * as React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "../remotion-shim";

export type PictogramType = "git" | "cli" | "jira" | "local" | "beads" | "virtual" | "vscode" | "wiki" | "policy";

export function AnimatedPictogramVideo({ type = "git", style }: { type?: PictogramType, style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Loop every 22 seconds
  const totalFrames = fps * 22;
  const loopFrame = frame % totalFrames;
  const pct = loopFrame / totalFrames;

  // Isometric helpers
  const Board = ({ y, opacity = 1, color = "var(--column)" }: { y: number; opacity?: number; color?: string }) => (
    <g transform={`translate(250, ${y}) scale(1, 0.5) rotate(45) translate(-100, -75)`} opacity={opacity}>
      {/* Board Base */}
      <rect width="200" height="150" fill={color} rx="8" />
      
      {/* Columns */}
      <rect x="10" y="10" width="54" height="130" fill="var(--background)" rx="4" />
      <rect x="73" y="10" width="54" height="130" fill="var(--background)" rx="4" />
      <rect x="136" y="10" width="54" height="130" fill="var(--background)" rx="4" />
    </g>
  );

  const Card = ({ x, y, z, fill = "var(--card)", opacity = 1, pulse = false }: { x: number; y: number; z: number; fill?: string; opacity?: number; pulse?: boolean }) => {
    const pulseOpacity = pulse ? interpolate(Math.sin(frame * 0.1), [-1, 1], [0.5, 1]) : opacity;
    return (
      <g transform={`translate(${x}, ${y}) scale(1, 0.5) rotate(45) translate(${z}, 0)`} opacity={pulseOpacity}>
        <rect width="44" height="20" fill={fill} rx="2" />
      </g>
    );
  };

  const renderGit = () => {
    // Helper for Framer Motion times mapping to interpolate
    const getInterpolated = (times: number[], values: number[]) => {
      return interpolate(pct, times, values, {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
    };

    // Layer 1
    const op1_1 = getInterpolated([0, 0.045, 0.068, 0.955, 0.977, 1], [0, 0, 1, 1, 0, 0]);
    const y1_2 = getInterpolated([0, 0.727, 0.750, 0.955, 0.977, 1], [0, 0, 25, 25, 0, 0]);
    const op1_2 = getInterpolated([0, 0.727, 0.750, 0.955, 0.977, 1], [1, 1, 1, 1, 0, 1]);
    const x1_3 = getInterpolated([0, 0.750, 0.773, 0.955, 0.977, 1], [0, 0, 63, 63, 0, 0]);
    const op1_3 = getInterpolated([0, 0.750, 0.773, 0.955, 0.977, 1], [1, 1, 1, 1, 0, 1]);

    // Layer 2
    const op2_1 = getInterpolated([0, 0.182, 0.205, 0.955, 0.977, 1], [0, 0, 1, 1, 0, 0]);
    const y2_2 = getInterpolated([0, 0.591, 0.614, 0.955, 0.977, 1], [0, 0, 25, 25, 0, 0]);
    const op2_2 = getInterpolated([0, 0.591, 0.614, 0.955, 0.977, 1], [1, 1, 1, 1, 0, 1]);
    const x2_3 = getInterpolated([0, 0.614, 0.636, 0.955, 0.977, 1], [0, 0, 63, 63, 0, 0]);
    const op2_3 = getInterpolated([0, 0.614, 0.636, 0.955, 0.977, 1], [1, 1, 1, 1, 0, 1]);

    // Layer 3
    const op3_1 = getInterpolated([0, 0.318, 0.341, 0.955, 0.977, 1], [0, 0, 1, 1, 0, 0]);
    const y3_2 = getInterpolated([0, 0.455, 0.477, 0.955, 0.977, 1], [0, 0, 25, 25, 0, 0]);
    const op3_2 = getInterpolated([0, 0.455, 0.477, 0.955, 0.977, 1], [1, 1, 1, 1, 0, 1]);
    const x3_3 = getInterpolated([0, 0.477, 0.500, 0.955, 0.977, 1], [0, 0, 63, 63, 0, 0]);
    const op3_3 = getInterpolated([0, 0.477, 0.500, 0.955, 0.977, 1], [1, 1, 1, 1, 0, 1]);

    return (
      <g>
        <line x1="80" y1="40" x2="80" y2="280" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4" />
        <text x="70" y="160" transform="rotate(-90 70 160)" textAnchor="middle" fill="var(--text-selected)" fontSize="12" fontFamily="monospace" fontWeight="bold" letterSpacing="2">GIT</text>
        
        {/* Layer 1 (Bottom) */}
        <g>
          <Board y="220" />
          <g transform="translate(250, 220) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <rect x="15" y="15" width="44" height="20" fill="var(--card)" rx="2" />
            <rect x="15" y="40" width="44" height="20" fill="var(--card)" rx="2" />
            <rect x="78" y="40" width="44" height="20" fill="var(--card)" rx="2" />
            <g opacity={op1_1}><rect x="15" y="65" width="44" height="20" fill="var(--text-selected)" rx="2" /></g>
            <g transform={`translate(0, ${y1_2})`} opacity={op1_2}><rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" /></g>
            <g transform={`translate(${x1_3}, 0)`} opacity={op1_3}><rect x="78" y="15" width="44" height="20" fill="var(--text-selected)" rx="2" /></g>
          </g>
        </g>

        {/* Layer 2 (Middle) */}
        <g>
          <Board y="150" />
          <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <rect x="15" y="15" width="44" height="20" fill="var(--card)" rx="2" />
            <rect x="15" y="40" width="44" height="20" fill="var(--card)" rx="2" />
            <rect x="78" y="40" width="44" height="20" fill="var(--card)" rx="2" />
            <g opacity={op2_1}><rect x="15" y="65" width="44" height="20" fill="var(--text-selected)" rx="2" /></g>
            <g transform={`translate(0, ${y2_2})`} opacity={op2_2}><rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" /></g>
            <g transform={`translate(${x2_3}, 0)`} opacity={op2_3}><rect x="78" y="15" width="44" height="20" fill="var(--text-selected)" rx="2" /></g>
          </g>
        </g>

        {/* Layer 3 (Top) */}
        <g>
          <Board y="80" />
          <g transform="translate(250, 80) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <rect x="15" y="15" width="44" height="20" fill="var(--card)" rx="2" />
            <rect x="15" y="40" width="44" height="20" fill="var(--card)" rx="2" />
            <rect x="78" y="40" width="44" height="20" fill="var(--card)" rx="2" />
            <g opacity={op3_1}><rect x="15" y="65" width="44" height="20" fill="var(--text-selected)" rx="2" /></g>
            <g transform={`translate(0, ${y3_2})`} opacity={op3_2}><rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" /></g>
            <g transform={`translate(${x3_3}, 0)`} opacity={op3_3}><rect x="78" y="15" width="44" height="20" fill="var(--text-selected)" rx="2" /></g>
          </g>
        </g>
      </g>
    );
  };

  const renderCli = () => {
    const cycle = (frame % (fps * 4)) / (fps * 4);
    const cardY = interpolate(cycle, [0.5, 0.7], [-50, -60], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
    const cardOp = interpolate(cycle, [0.5, 0.7], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

    return (
      <g>
        <Board y="150" />
        <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
          <rect x="15" y="15" width="44" height="20" fill="var(--card)" rx="2" />
          <rect x="78" y="15" width="44" height="20" fill="var(--card)" rx="2" />
        </g>
        
        {/* Terminal Window Isometric */}
        <g transform="translate(100, 250) scale(1, 0.5) rotate(45) translate(-80, -40)">
          <rect width="160" height="80" fill="var(--column)" rx="4" stroke="var(--border)" strokeWidth="2" />
          <rect width="160" height="20" fill="var(--background)" rx="4" />
          <path d="M 0 16 L 160 16" fill="none" stroke="var(--border)" strokeWidth="2" />
          <circle cx="15" cy="8" r="3" fill="var(--text-muted)" />
          <circle cx="25" cy="8" r="3" fill="var(--text-muted)" />
          <circle cx="35" cy="8" r="3" fill="var(--text-muted)" />
          <text x="10" y="40" fill="var(--text-selected)" fontSize="10" fontFamily="monospace">~❯</text>
          <text x="25" y="40" fill="var(--text-muted)" fontSize="10" fontFamily="monospace">kanbus</text>
          <line x1="68" y1="32" x2="68" y2="42" stroke="var(--text-selected)" strokeWidth="2">
            <animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite" />
          </line>
        </g>

        {/* Line from terminal to board */}
        <line x1="250" y1="220" x2="250" y2="150" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </line>

        {/* Card appearing */}
        <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
          <g transform={`translate(0, ${cardY})`} opacity={cardOp}>
             <rect x="15" y="90" width="44" height="20" fill="var(--text-selected)" rx="2" />
          </g>
        </g>
      </g>
    );
  };

  const renderJira = () => {
    return (
      <g>
        <Board y="150" />
        
        {/* Jira Node */}
        <g transform="translate(100, 150) scale(1, 0.5) rotate(45) translate(-40, -40)">
          <rect width="80" height="80" fill="var(--column)" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4" rx="16" />
          <path d="M 28 35 C 28 27 34 22 40 22 C 46 22 52 27 52 35 C 52 40 49 45 44 48 C 38 52 35 58 35 62 L 35 65" fill="none" stroke="var(--text-selected)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        </g>

        {/* Sync lines */}
        <path d="M 100 150 L 250 150" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="6 6">
          <animate attributeName="stroke-dashoffset" from="12" to="0" dur="1s" repeatCount="indefinite" />
        </path>
        
        {/* Syncing cards */}
        <Card x={interpolate(frame % (fps*2), [0, fps*2], [100, 250])} y={150} z={-10} fill="var(--card)" pulse />
      </g>
    );
  };

  const renderLocal = () => {
    return (
      <g>
        {/* Local Board (Dashed/Transparent) */}
        <g transform={`translate(150, 200) scale(1, 0.5) rotate(45) translate(-100, -75)`} opacity={0.6}>
          <rect width="200" height="150" fill="transparent" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4" rx="8" />
          <rect x="10" y="10" width="54" height="130" fill="var(--background)" rx="4" />
          <rect x="15" y="15" width="44" height="20" fill="var(--card)" rx="2" />
        </g>
        
        {/* Shared Board */}
        <Board y="100" />
        <g transform="translate(250, 100) scale(1, 0.5) rotate(45) translate(-100, -75)">
          <rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" />
        </g>

        {/* Promotion Arrow */}
        <path d="M 150 200 L 250 100" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </path>

        <Card x={interpolate(frame % (fps*3), [0, fps*3], [150, 250])} y={interpolate(frame % (fps*3), [0, fps*3], [200, 100])} z={0} fill="var(--text-selected)" />
      </g>
    );
  };

  const renderBeads = () => {
    return (
      <g>
        <Board y="150" />
        
        {/* Markdown File */}
        <g transform="translate(100, 250) scale(1, 0.5) rotate(45) translate(-30, -40)">
          <path d="M 0 0 L 45 0 L 60 15 L 60 80 L 0 80 Z" fill="var(--background)" stroke="var(--border)" strokeWidth="2" strokeLinejoin="round" />
          <path d="M 45 0 L 45 15 L 60 15" fill="none" stroke="var(--border)" strokeWidth="2" strokeLinejoin="round" />
          <line x1="10" y1="20" x2="40" y2="20" stroke="var(--text-selected)" strokeWidth="2" strokeLinecap="round" />
          <line x1="10" y1="35" x2="50" y2="35" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <line x1="10" y1="50" x2="50" y2="50" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <line x1="10" y1="65" x2="35" y2="65" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
        </g>

        <path d="M 100 250 L 250 150" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </path>

        {/* Magic Wand / Morph effect */}
        <Card x={interpolate(frame % (fps*3), [0, fps*3], [100, 250])} y={interpolate(frame % (fps*3), [0, fps*3], [250, 150])} z={0} fill="var(--text-selected)" />
      </g>
    );
  };

  const renderVirtual = () => {
    return (
      <g>
        {/* Unified Board */}
        <Board y="100" opacity={1} />
        
        {/* Incoming Boards */}
        <Board y="250" opacity={0.6} color="var(--card-muted)" />
        <Board y="350" opacity={0.4} color="var(--card-muted)" />

        <path d="M 250 250 L 250 100" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </path>

        <path d="M 250 350 L 250 250" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </path>

        <Card x={250} y={interpolate(frame % (fps*2), [0, fps*2], [250, 100])} z={-20} fill="var(--text-selected)" opacity={0.8} />
        <Card x={250} y={interpolate(frame % (fps*2), [0, fps*2], [350, 250])} z={20} fill="var(--text-selected)" opacity={0.6} />
      </g>
    );
  };

  const renderVsCode = () => {
    return (
      <g>
        {/* VS Code Window Isometric */}
        <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-150, -100)">
          <rect width="300" height="200" fill="var(--background)" rx="4" stroke="var(--border)" strokeWidth="2" />
          <rect width="300" height="20" fill="var(--card)" rx="4" />
          <path d="M 0 20 L 300 20" fill="none" stroke="var(--border)" strokeWidth="2" />
          <circle cx="15" cy="10" r="4" fill="var(--text-muted)" />
          <circle cx="30" cy="10" r="4" fill="var(--text-muted)" />
          <circle cx="45" cy="10" r="4" fill="var(--text-muted)" />
          
          {/* Sidebar */}
          <rect x="0" y="20" width="60" height="180" fill="var(--card-muted)" />
          <line x1="60" y1="20" x2="60" y2="200" stroke="var(--border)" strokeWidth="2" />
          
          {/* Editor Area (Kanbus Board) */}
          <rect x="70" y="30" width="220" height="160" fill="var(--column)" rx="4" />
          <rect x="80" y="40" width="60" height="140" fill="var(--background)" rx="2" />
          <rect x="150" y="40" width="60" height="140" fill="var(--background)" rx="2" />
          <rect x="220" y="40" width="60" height="140" fill="var(--background)" rx="2" />

          {/* Animated Card */}
          <rect x="85" y={interpolate(Math.sin(frame * 0.05), [-1, 1], [45, 120])} width="50" height="25" fill="var(--text-selected)" rx="2" />
        </g>
      </g>
    );
  };

  const renderPolicy = () => {
    // A checklist/clipboard checking off items
    const cycle = (frame % (fps * 3)) / (fps * 3);
    const drawCheck1 = interpolate(cycle, [0.1, 0.2], [0, 100], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
    const drawCheck2 = interpolate(cycle, [0.4, 0.5], [0, 100], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
    const drawCheck3 = interpolate(cycle, [0.7, 0.8], [0, 100], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

    return (
      <g>
        <Board y="150" />
        
        {/* Clipboard */}
        <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(0, -20)">
          {/* Clipboard Board */}
          <rect width="70" height="90" fill="var(--card-muted)" rx="4" stroke="var(--border)" strokeWidth="2" />
          {/* Clip */}
          <rect x="25" y="-5" width="20" height="10" fill="var(--text-muted)" rx="2" />
          
          {/* Item 1 */}
          <rect x="10" y="20" width="10" height="10" fill="var(--background)" stroke="var(--text-muted)" strokeWidth="1" rx="2" />
          <line x1="28" y1="25" x2="60" y2="25" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <path d="M 12 25 L 14 28 L 18 22" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="100" strokeDashoffset={100 - drawCheck1} />

          {/* Item 2 */}
          <rect x="10" y="40" width="10" height="10" fill="var(--background)" stroke="var(--text-muted)" strokeWidth="1" rx="2" />
          <line x1="28" y1="45" x2="50" y2="45" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <path d="M 12 45 L 14 48 L 18 42" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="100" strokeDashoffset={100 - drawCheck2} />

          {/* Item 3 */}
          <rect x="10" y="60" width="10" height="10" fill="var(--background)" stroke="var(--text-muted)" strokeWidth="1" rx="2" />
          <line x1="28" y1="65" x2="55" y2="65" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <path d="M 12 65 L 14 68 L 18 62" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="100" strokeDashoffset={100 - drawCheck3} />
        </g>
        
        {/* Card connecting to checklist */}
        <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
          <g transform={`translate(${interpolate(cycle, [0, 1], [15, 63])}, 65)`}>
            <rect x="0" y="0" width="44" height="20" fill="var(--text-selected)" rx="2" />
          </g>
        </g>
      </g>
    );
  };

  const renderWiki = () => {
    const cycle = (frame % (fps * 3)) / (fps * 3);
    const cardY = interpolate(cycle, [0, 0.5, 1], [205, 165, 150]);

    return (
      <g>
        <Board y="150" />

        {/* Wiki document node */}
        <g transform="translate(120, 225) scale(1, 0.5) rotate(45) translate(-45, -58)">
          <path d="M 0 0 L 66 0 L 82 16 L 82 116 L 0 116 Z" fill="var(--background)" stroke="var(--border)" strokeWidth="2" strokeLinejoin="round" />
          <path d="M 66 0 L 66 16 L 82 16" fill="none" stroke="var(--border)" strokeWidth="2" strokeLinejoin="round" />
          <line x1="12" y1="24" x2="58" y2="24" stroke="var(--text-selected)" strokeWidth="2" strokeLinecap="round" />
          <line x1="12" y1="40" x2="68" y2="40" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <line x1="12" y1="56" x2="68" y2="56" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <line x1="12" y1="72" x2="54" y2="72" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          <line x1="12" y1="88" x2="62" y2="88" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
        </g>

        {/* Sync path from wiki to board */}
        <path d="M 120 225 L 250 150" fill="none" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="5 5">
          <animate attributeName="stroke-dashoffset" from="10" to="0" dur="1s" repeatCount="indefinite" />
        </path>

        {/* Highlight card materializing on board */}
        <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
          <rect x="15" y={cardY} width="44" height="20" fill="var(--text-selected)" rx="2" />
        </g>
      </g>
    );
  };

  const contentMap: Record<PictogramType, { title: string, render: () => React.ReactNode }> = {
    git: { title: "Git Synchronization", render: renderGit },
    cli: { title: "Core Management", render: renderCli },
    jira: { title: "Jira Sync", render: renderJira },
    local: { title: "Local Tasks", render: renderLocal },
    beads: { title: "Beads Compatibility", render: renderBeads },
    virtual: { title: "Virtual Projects", render: renderVirtual },
    vscode: { title: "VS Code Integration", render: renderVsCode },
    wiki: { title: "Integrated Wiki", render: renderWiki },
    policy: { title: "Policy as Code", render: renderPolicy },
  };

  const { render } = contentMap[type] || contentMap.git;

  return (
    <div style={{
      backgroundColor: "var(--card)",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "32px",
      overflow: "hidden",
      borderRadius: "16px",
      minHeight: "500px",
      ...(style || { width: "100%", height: "100%" })
    }}>
      <svg width="100%" height="450" viewBox="0 0 500 350" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <radialGradient id="pictogram-glow" cx="50%" cy="50%" r="50%" fx="50%" fy="50%">
            <stop offset="0%" stopColor="var(--glow-center)" />
            <stop offset="100%" stopColor="var(--glow-edge)" />
          </radialGradient>
        </defs>
        
        {/* Ambient background glow / shadow */}
        <ellipse cx="250" cy="150" rx="200" ry="140" fill="url(#pictogram-glow)" />
        
        {render()}
      </svg>
    </div>
  );
}
