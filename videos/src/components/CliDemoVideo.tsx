import * as React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "../remotion-shim";

const COMMANDS = [
  {
    cmd: "kanbus create \"Implement auth flow\"",
    output: "Created epic PROJ-1a2b3c: Implement auth flow"
  },
  {
    cmd: "kanbus create --parent PROJ-1a2b3c \"Add OAuth login\"",
    output: "Created task PROJ-4d5e6f: Add OAuth login"
  },
  {
    cmd: "kanbus update PROJ-4d5e6f --status in_progress",
    output: "Updated PROJ-4d5e6f: status = in_progress"
  },
  {
    cmd: "kanbus list --status in_progress",
    output: "PROJ-4d5e6f: Add OAuth login [In Progress]"
  }
];

export function CliDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Change every 4 seconds
  const intervalFrames = fps * 4;
  const activeIndex = Math.floor(frame / intervalFrames) % COMMANDS.length;
  const transitionFrame = frame % intervalFrames;

  // Typewriter effect for the command
  const typeDuration = fps * 1.5;
  const charsToShow = Math.min(
    COMMANDS[activeIndex].cmd.length,
    Math.floor(interpolate(transitionFrame, [0, typeDuration], [0, COMMANDS[activeIndex].cmd.length], { extrapolateRight: "clamp" }))
  );

  // Show output slightly after typing finishes
  const showOutput = transitionFrame > typeDuration + (fps * 0.2);
  const outputOpacity = showOutput ? 
    interpolate(transitionFrame - (typeDuration + fps * 0.2), [0, fps * 0.2], [0, 1], { extrapolateRight: "clamp" }) : 0;

  return (
    <div className="absolute flex justify-center items-center p-8" style={style || { inset: 0 }}>
      {/* Background glow to ground the 3D window */}
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] rounded-[100%] pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
        }}
      />
      
      <div className="relative w-full max-w-4xl bg-[var(--card)] rounded-xl overflow-hidden shadow-2xl font-mono text-lg flex flex-col border border-border">
        <div className="bg-[var(--card-muted)] px-4 py-3 flex items-center gap-2 border-b border-black/50">
          <div className="w-3 h-3 rounded-full bg-red-500"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
          <div className="w-3 h-3 rounded-full bg-green-500"></div>
          <div className="ml-4 text-xs text-[var(--text-foreground)] font-sans">Terminal - kanbus</div>
        </div>
        
        <div className="p-6 h-[300px] text-green-400 relative">
          <div className="flex flex-col gap-4">
            {/* Show previous commands faintly */}
            {activeIndex > 0 && (
              <div className="opacity-30">
                <div className="flex gap-2">
                  <span className="text-blue-400">~</span>
                  <span className="text-pink-400">❯</span>
                  <span className="text-white">{COMMANDS[activeIndex - 1].cmd}</span>
                </div>
                <div className="text-neutral-300 mt-1 pl-6">
                  {COMMANDS[activeIndex - 1].output}
                </div>
              </div>
            )}

            {/* Active command */}
            <div>
              <div className="flex gap-2 items-center">
                <span className="text-blue-400">~</span>
                <span className="text-pink-400">❯</span>
                <span className="text-white">
                  {COMMANDS[activeIndex].cmd.substring(0, charsToShow)}
                  {transitionFrame < typeDuration + (fps * 0.5) && (
                    <span className="w-2.5 h-5 bg-white/70 inline-block ml-1 align-middle animate-pulse"></span>
                  )}
                </span>
              </div>
              
              {/* Output */}
              <div 
                className="text-neutral-300 mt-2 pl-6 transition-opacity"
                style={{ opacity: outputOpacity }}
              >
                {COMMANDS[activeIndex].output}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
