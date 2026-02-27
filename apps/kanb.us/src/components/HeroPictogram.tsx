import * as React from "react";
import { motion } from "framer-motion";

export function HeroPictogram() {
  return (
    <div className="w-full aspect-video bg-black flex items-center justify-center relative overflow-hidden rounded-xl">
      {/* UI State */}
      <motion.svg
        width="100%"
        height="100%"
        viewBox="0 0 400 300"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="absolute inset-0"
        animate={{ opacity: [1, 1, 0, 0, 1] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
      >
        <g transform="translate(40, 20)">
            {/* Kanban Board background */}
            <rect x="0" y="0" width="320" height="260" fill="var(--column)" rx="12" />
            
            {/* Column 1 */}
            <rect x="12" y="12" width="90" height="236" fill="var(--background)" rx="6" />
            <rect x="20" y="20" width="74" height="32" fill="var(--card)" rx="4" />
            <rect x="20" y="60" width="74" height="32" fill="var(--card)" rx="4" />
            <rect x="20" y="100" width="74" height="32" fill="var(--card)" rx="4" />
            
            {/* Column 2 */}
            <rect x="114" y="12" width="90" height="236" fill="var(--background)" rx="6" />
            <rect x="122" y="20" width="74" height="32" fill="var(--text-selected)" rx="4" />
            <rect x="122" y="60" width="74" height="32" fill="var(--card)" rx="4" />
            
            {/* Column 3 */}
            <rect x="216" y="12" width="90" height="236" fill="var(--background)" rx="6" />
            <rect x="224" y="20" width="74" height="32" fill="var(--card)" rx="4" />
        </g>
      </motion.svg>

      {/* JSON State */}
      <motion.svg
        width="100%"
        height="100%"
        viewBox="0 0 400 300"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="absolute inset-0 font-mono text-[22px] font-bold"
        animate={{ opacity: [0, 0, 1, 1, 0] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
      >
        <g transform="translate(40, 20)">
            <rect x="0" y="0" width="320" height="260" fill="var(--column)" rx="12" />
            
            <text x="24" y="32" fill="var(--text-muted)">[</text>
            
            {/* First item */}
            <text x="40" y="64" fill="var(--text-muted)">{`{`}</text>
            <text x="60" y="96" fill="var(--text-muted)">"</text>
            <rect x="76" y="80" width="30" height="16" fill="var(--text-selected)" rx="4" />
            <text x="108" y="96" fill="var(--text-muted)">": "</text>
            <rect x="144" y="80" width="60" height="16" fill="var(--card-muted)" rx="4" />
            <text x="206" y="96" fill="var(--text-muted)">",</text>
            
            <text x="60" y="128" fill="var(--text-muted)">"</text>
            <rect x="76" y="112" width="45" height="16" fill="var(--text-selected)" rx="4" />
            <text x="123" y="128" fill="var(--text-muted)">": "</text>
            <rect x="159" y="112" width="40" height="16" fill="var(--card-muted)" rx="4" />
            <text x="201" y="128" fill="var(--text-muted)">"</text>
            
            <text x="40" y="160" fill="var(--text-muted)">{`},`}</text>

            {/* Second item */}
            <text x="40" y="192" fill="var(--text-muted)">{`{`}</text>
            <text x="60" y="224" fill="var(--text-muted)">"</text>
            <rect x="76" y="208" width="35" height="16" fill="var(--text-selected)" rx="4" />
            <text x="113" y="224" fill="var(--text-muted)">": "</text>
            <rect x="149" y="208" width="50" height="16" fill="var(--card-muted)" rx="4" />
            <text x="201" y="224" fill="var(--text-muted)">"</text>
            
            <text x="40" y="256" fill="var(--text-muted)">{`}`}</text>

            <text x="24" y="288" fill="var(--text-muted)">]</text>
        </g>
      </motion.svg>
    </div>
  );
}
