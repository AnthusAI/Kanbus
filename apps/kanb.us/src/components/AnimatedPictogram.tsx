import * as React from "react";
import { motion } from "framer-motion";

export function AnimatedPictogram() {
  const transitionProps = {
    duration: 3,
    ease: "easeInOut",
    repeat: Infinity,
    times: [0, 0.2, 0.4, 0.8, 1] // Timing for each stage
  };

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

  return (
    <div className="w-full h-full bg-card flex flex-col items-center justify-center p-8 overflow-hidden rounded-2xl min-h-[500px]">
      <h3 className="font-mono text-sm text-muted mb-4 tracking-widest uppercase">Git Synchronization</h3>
      <svg width="100%" height="450" viewBox="0 0 500 350" fill="none" xmlns="http://www.w3.org/2000/svg">
        
        {/* Connection Line (Git) */}
        <line x1="80" y1="40" x2="80" y2="280" stroke="var(--text-selected)" strokeWidth="2" strokeDasharray="4 4" />
        <text x="70" y="160" transform="rotate(-90 70 160)" textAnchor="middle" fill="var(--text-selected)" fontSize="12" fontFamily="monospace" fontWeight="bold" letterSpacing="2">GIT</text>
        
        {/* Layer 1 (Bottom) - Developer A */}
        <g>
          <Board y="220" />
          {/* Scenario 1: New Item appearing */}
          <g transform="translate(250, 220) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0, 1, 1, 0, 0] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.045, 0.068, 0.955, 0.977, 1]
              }}
            >
              <rect x="15" y="65" width="44" height="20" fill="var(--text-selected)" rx="2" />
            </motion.g>
          </g>
          {/* Scenario 2: Existing right column card - Shifts down */}
          <g transform="translate(250, 220) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              animate={{ y: [0, 0, 25, 25, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.727, 0.750, 0.955, 0.977, 1]
              }}
            >
              <rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" />
            </motion.g>
          </g>
          {/* Scenario 2: Moving Card - syncs move */}
          <g transform="translate(250, 220) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              animate={{ x: [0, 0, 63, 63, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.750, 0.773, 0.955, 0.977, 1]
              }}
            >
              <rect x="78" y="15" width="44" height="20" fill="var(--text-selected)" rx="2" />
            </motion.g>
          </g>
        </g>

        {/* Layer 2 (Middle) - Web Console */}
        <g>
          <Board y="150" />
          {/* Scenario 1: New Item appearing */}
          <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0, 1, 1, 0, 0] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.182, 0.205, 0.955, 0.977, 1]
              }}
            >
              <rect x="15" y="65" width="44" height="20" fill="var(--text-selected)" rx="2" />
            </motion.g>
          </g>
          {/* Scenario 2: Existing right column card - Shifts down */}
          <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              animate={{ y: [0, 0, 25, 25, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.591, 0.614, 0.955, 0.977, 1]
              }}
            >
              <rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" />
            </motion.g>
          </g>
          {/* Scenario 2: Moving Card - syncs move */}
          <g transform="translate(250, 150) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              animate={{ x: [0, 0, 63, 63, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.614, 0.636, 0.955, 0.977, 1]
              }}
            >
              <rect x="78" y="15" width="44" height="20" fill="var(--text-selected)" rx="2" />
            </motion.g>
          </g>
        </g>

        {/* Layer 3 (Top) - AI Agent */}
        <g>
          <Board y="80" />
          {/* Scenario 1: New Item appearing */}
          <g transform="translate(250, 80) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0, 1, 1, 0, 0] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.318, 0.341, 0.955, 0.977, 1]
              }}
            >
              <rect x="15" y="65" width="44" height="20" fill="var(--text-selected)" rx="2" />
            </motion.g>
          </g>
          {/* Scenario 2: Existing right column card - Shifts down */}
          <g transform="translate(250, 80) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              animate={{ y: [0, 0, 25, 25, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.455, 0.477, 0.955, 0.977, 1]
              }}
            >
              <rect x="141" y="15" width="44" height="20" fill="var(--card)" rx="2" />
            </motion.g>
          </g>
          {/* Scenario 2: Moving Card - initiates move */}
          <g transform="translate(250, 80) scale(1, 0.5) rotate(45) translate(-100, -75)">
            <motion.g
              animate={{ x: [0, 0, 63, 63, 0, 0], opacity: [1, 1, 1, 1, 0, 1] }}
              transition={{
                duration: 22,
                ease: "easeInOut",
                repeat: Infinity,
                times: [0, 0.477, 0.500, 0.955, 0.977, 1]
              }}
            >
              <rect x="78" y="15" width="44" height="20" fill="var(--text-selected)" rx="2" />
            </motion.g>
          </g>
        </g>

      </svg>
    </div>
  );
}
