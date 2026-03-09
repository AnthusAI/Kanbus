import * as React from "react";
import { motion } from "framer-motion";

function lerpKf(values: number[], times: number[], t: number): number {
  const n = times.length;
  if (t <= times[0]) return values[0];
  if (t >= times[n - 1]) return values[n - 1];
  for (let i = 0; i < n - 1; i++) {
    if (t >= times[i] && t <= times[i + 1]) {
      const seg = times[i + 1] - times[i];
      if (seg === 0) return values[i + 1];
      return values[i] + ((t - times[i]) / seg) * (values[i + 1] - values[i]);
    }
  }
  return values[n - 1];
}

export function AnimatedPictogram({ frame, fps, showTitle, framed, className, style }: {
  frame?: number; fps?: number;
  showTitle?: boolean; framed?: boolean;
  className?: string; style?: React.CSSProperties;
}) {
  const frameTimeSec = (frame != null && fps != null && fps > 0) ? frame / fps : null;

  const Board = ({ y, opacity = 1 }: { y: number; opacity?: number }) => (
    <g transform={`translate(250, ${y}) scale(1, 0.5) rotate(45) translate(-100, -75)`} opacity={opacity}>
      {/* Board Base */}
      <rect width="200" height="150" fill="var(--column)" rx="8" />
      
      {/* Columns */}
      <rect x="10" y="10" width="54" height="130" fill="var(--background)" rx="4" />
      <rect x="73" y="10" width="54" height="130" fill="var(--background)" rx="4" />
      <rect x="136" y="10" width="54" height="130" fill="var(--background)" rx="4" />

      {/* Existing Cards (Static) - Except the ones we'll animate */}
      <rect x="15" y="15" width="44" height="20" fill="var(--card)" rx="2" />
      <rect x="15" y="40" width="44" height="20" fill="var(--card)" rx="2" />
      <rect x="78" y="40" width="44" height="20" fill="var(--card)" rx="2" />
      {/* 78x15 is animated (Scenario 2) */}
      {/* 141x15 is animated (Scenario 2) */}
    </g>
  );

  const DUR = 22;

  // Per-layer keyframe times for each animation type
  const layers = [
    { boardY: 220, newTimes: [0, 0.045, 0.068, 0.955, 0.977, 1], downTimes: [0, 0.727, 0.750, 0.955, 0.977, 1], moveTimes: [0, 0.750, 0.773, 0.955, 0.977, 1] },
    { boardY: 150, newTimes: [0, 0.182, 0.205, 0.955, 0.977, 1], downTimes: [0, 0.591, 0.614, 0.955, 0.977, 1], moveTimes: [0, 0.614, 0.636, 0.955, 0.977, 1] },
    { boardY: 80,  newTimes: [0, 0.318, 0.341, 0.955, 0.977, 1], downTimes: [0, 0.455, 0.477, 0.955, 0.977, 1], moveTimes: [0, 0.477, 0.500, 0.955, 0.977, 1] },
  ];

  const renderLayer = (layer: typeof layers[0], t: number | null) => {
    const { boardY, newTimes, downTimes, moveTimes } = layer;
    if (t != null) {
      const newOp  = lerpKf([0, 0, 1, 1, 0, 0], newTimes, t);
      const downY  = lerpKf([0, 0, 25, 25, 0, 0], downTimes, t);
      const downOp = lerpKf([1, 1, 1, 1, 0, 1], downTimes, t);
      const moveX  = lerpKf([0, 0, 63, 63, 0, 0], moveTimes, t);
      const moveOp = lerpKf([1, 1, 1, 1, 0, 1], moveTimes, t);
      return (
        <g transform="translate(-15, 0) scale(1.15) translate(-35, -20)">
          <Board y={boardY} />
          <g transform={`translate(250, ${boardY}) scale(1, 0.5) rotate(45) translate(-100, -75)`}>
            <g opacity={newOp}><rect x="15" y="65" width="44" height="20" fill="var(--accent-blue)" rx="2" /></g>
          </g>
          <g transform={`translate(250, ${boardY}) scale(1, 0.5) rotate(45) translate(-100, -75)`}>
            <g transform={`translate(0, ${downY})`} opacity={downOp}><rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" /></g>
          </g>
          <g transform={`translate(250, ${boardY}) scale(1, 0.5) rotate(45) translate(-100, -75)`}>
            <g transform={`translate(${moveX}, 0)`} opacity={moveOp}><rect x="78" y="15" width="44" height="20" fill="var(--accent-blue)" rx="2" /></g>
          </g>
        </g>
      );
    }
    return (
      <g transform="translate(-15, 0) scale(1.15) translate(-35, -20)">
        <Board y={boardY} />
        <g transform={`translate(250, ${boardY}) scale(1, 0.5) rotate(45) translate(-100, -75)`}>
          <motion.g initial={{ opacity: 0 }} animate={{ opacity: [0, 0, 1, 1, 0, 0] }} transition={{ duration: DUR, ease: "easeInOut", repeat: Infinity, times: newTimes }}>
            <rect x="15" y="65" width="44" height="20" fill="var(--accent-blue)" rx="2" />
          </motion.g>
        </g>
        <g transform={`translate(250, ${boardY}) scale(1, 0.5) rotate(45) translate(-100, -75)`}>
          <motion.g animate={{ y: [0, 0, 25, 25, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }} transition={{ duration: DUR, ease: "easeInOut", repeat: Infinity, times: downTimes }}>
            <rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" />
          </motion.g>
        </g>
        <g transform={`translate(250, ${boardY}) scale(1, 0.5) rotate(45) translate(-100, -75)`}>
          <motion.g animate={{ x: [0, 0, 63, 63, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }} transition={{ duration: DUR, ease: "easeInOut", repeat: Infinity, times: moveTimes }}>
            <rect x="78" y="15" width="44" height="20" fill="var(--accent-blue)" rx="2" />
          </motion.g>
        </g>
      </g>
    );
  };

  const t = frameTimeSec != null ? (frameTimeSec % DUR) / DUR : null;

  return (
    <div className={`w-full h-full bg-card flex flex-col items-center justify-center py-6 px-2 md:p-8 overflow-hidden rounded-2xl min-h-[400px] relative pictogram ${className || ""}`} style={style}>
      {/* Background glow to ground the 3D window */}
      <div
        className="absolute top-[60%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-[100%] pointer-events-none z-0"
        style={{ background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)" }}
      />
      {showTitle !== false && <h3 className="font-mono text-sm text-muted mb-4 tracking-widest uppercase z-10">Git Synchronization</h3>}
      <svg width="100%" viewBox="55 0 335 300" fill="none" xmlns="http://www.w3.org/2000/svg" className="z-10 h-auto max-h-[400px]">
        <defs>
          <radialGradient id="pictogram-glow" cx="50%" cy="50%" r="50%" fx="50%" fy="50%">
            <stop offset="0%" stopColor="var(--glow-center)" />
            <stop offset="100%" stopColor="var(--glow-edge)" />
          </radialGradient>
        </defs>
        <ellipse cx="250" cy="150" rx="200" ry="140" fill="url(#pictogram-glow)" />
        <line x1="80" y1="40" x2="80" y2="280" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="4 4" />
        <path d="M 75 45 L 80 40 L 85 45" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M 75 275 L 80 280 L 85 275" fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <text x="70" y="160" transform="rotate(-90 70 160)" textAnchor="middle" fill="var(--accent-blue)" fontSize="12" fontFamily="monospace" fontWeight="bold" letterSpacing="2">GIT</text>
        {layers.map((layer, i) => <React.Fragment key={i}>{renderLayer(layer, t)}</React.Fragment>)}
      </svg>
    </div>
  );
}
