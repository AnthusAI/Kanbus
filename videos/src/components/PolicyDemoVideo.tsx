import * as React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "../remotion-shim";

export function PolicyDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Sequence:
  // 1. Show Gherkin policy code
  // 2. Someone tries to break it
  // 3. Error is thrown and blocked

  const stage1End = fps * 2;
  const stage2End = fps * 4;

  const policyOpacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });
  const policyY = interpolate(frame, [0, 10], [20, 0], { extrapolateRight: "clamp" });

  // Stage 2: CLI Command
  const cmdOpacity = interpolate(frame, [stage1End, stage1End + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const cmdString = "kanbus update task-123 --status in_progress";
  const cmdChars = Math.floor(interpolate(frame, [stage1End + 10, stage1End + fps], [0, cmdString.length], { extrapolateRight: "clamp" }));

  // Stage 3: Error
  const errorOpacity = interpolate(frame, [stage2End, stage2End + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const gherkinCode = `Feature: Tasks require assignee

  Scenario: Task must have assignee to start
    Given the issue type is "task"
    When transitioning to "in_progress"
    Then the issue must have field "assignee"`;

  return (
    <div className="absolute flex flex-col md:flex-row gap-8 justify-center items-center p-8 h-[500px]" style={style || { inset: 0 }}>
      
      {/* Policy File */}
      <div 
        className="flex-1 w-full max-w-md bg-[var(--card)] rounded-xl overflow-hidden shadow-2xl flex z-10 flex-col border border-border"
        style={{ opacity: policyOpacity, transform: `translateY(${policyY}px)` }}
      >
        <div className="bg-[var(--card-muted)] px-4 py-2 border-b border-black/50 text-xs text-green-400 font-mono flex items-center">
          <span className="mr-2">📄</span> require-assignee.policy
        </div>
        <div className="p-6 h-full flex items-center">
          <pre className="text-sm font-mono text-neutral-300 leading-relaxed whitespace-pre-wrap">
            <span className="text-purple-400">Feature:</span> Tasks require assignee{'\n\n'}
            <span className="text-blue-400">  Scenario:</span> Task must have assignee to start{'\n'}
            <span className="text-yellow-400">    Given</span> the issue type is <span className="text-green-300">"task"</span>{'\n'}
            <span className="text-yellow-400">    When</span> transitioning to <span className="text-green-300">"in_progress"</span>{'\n'}
            <span className="text-yellow-400">    Then</span> the issue must have field <span className="text-green-300">"assignee"</span>
          </pre>
        </div>
      </div>

      {/* Terminal Interaction */}
      <div className="flex-1 w-full max-w-md flex flex-col justify-center gap-4">
        
        <div 
          className="w-full bg-[var(--card)] rounded-xl overflow-hidden shadow-2xl font-mono text-lg border border-border"
          style={{ opacity: cmdOpacity }}
        >
          <div className="p-4 flex items-center text-green-400">
            <span className="text-blue-400 mr-2">~</span>
            <span className="text-pink-400 mr-2">❯</span>
            <span className="text-white text-sm">
              {cmdString.substring(0, Math.max(0, cmdChars))}
              <span className="w-2 h-4 bg-white/70 inline-block ml-1 align-middle animate-pulse"></span>
            </span>
          </div>

          <div 
            className="px-4 pb-4 pt-0 text-red-400 text-xs"
            style={{ opacity: errorOpacity }}
          >
            <div>Error: policy violation in require-assignee.policy</div>
            <div className="text-[var(--text-foreground)] ml-2 mt-1">Scenario: Task must have assignee to start</div>
            <div className="text-[var(--text-foreground)] ml-2">Failed: Then the issue must have field "assignee"</div>
            <div className="text-white ml-2 mt-1 border-l-2 border-red-500 pl-2">issue does not have field "assignee" set</div>
          </div>
        </div>

      </div>

    </div>
  );
}
