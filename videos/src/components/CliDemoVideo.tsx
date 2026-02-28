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

  const intervalFrames = fps * 4;
  const activeIndex = Math.floor(frame / intervalFrames) % COMMANDS.length;
  const transitionFrame = frame % intervalFrames;

  const typeDuration = fps * 1.5;
  const charsToShow = Math.min(
    COMMANDS[activeIndex].cmd.length,
    Math.floor(interpolate(transitionFrame, [0, typeDuration], [0, COMMANDS[activeIndex].cmd.length], { extrapolateRight: "clamp" }))
  );

  const showOutput = transitionFrame > typeDuration + (fps * 0.2);
  const outputOpacity = showOutput ?
    interpolate(transitionFrame - (typeDuration + fps * 0.2), [0, fps * 0.2], [0, 1], { extrapolateRight: "clamp" }) : 0;

  return (
    <div style={{
      position: "absolute",
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      padding: "32px",
      ...(style || { inset: 0 })
    }}>
      {/* Background glow */}
      <div style={{
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        width: "800px",
        height: "400px",
        borderRadius: "100%",
        pointerEvents: "none",
        background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)"
      }} />

      <div style={{
        position: "relative",
        width: "100%",
        maxWidth: "896px",
        backgroundColor: "var(--card)",
        borderRadius: "12px",
        overflow: "hidden",
        fontFamily: "monospace",
        fontSize: "18px",
        display: "flex",
        flexDirection: "column",
        border: "1px solid var(--border)"
      }}>
        {/* Title bar */}
        <div style={{
          backgroundColor: "var(--card-muted)",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          borderBottom: "1px solid rgba(0,0,0,0.5)"
        }}>
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "#ef4444" }} />
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "#eab308" }} />
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "#22c55e" }} />
          <div style={{ marginLeft: "16px", fontSize: "12px", color: "var(--text-foreground)", fontFamily: "sans-serif" }}>
            Terminal - kanbus
          </div>
        </div>

        {/* Terminal body */}
        <div style={{ padding: "24px", height: "300px", color: "#4ade80", position: "relative" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {/* Previous command (faint) */}
            {activeIndex > 0 && (
              <div style={{ opacity: 0.3 }}>
                <div style={{ display: "flex", gap: "8px" }}>
                  <span style={{ color: "#60a5fa" }}>~</span>
                  <span style={{ color: "#f472b6" }}>❯</span>
                  <span style={{ color: "#ffffff" }}>{COMMANDS[activeIndex - 1].cmd}</span>
                </div>
                <div style={{ color: "#d4d4d4", marginTop: "4px", paddingLeft: "24px" }}>
                  {COMMANDS[activeIndex - 1].output}
                </div>
              </div>
            )}

            {/* Active command */}
            <div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <span style={{ color: "#60a5fa" }}>~</span>
                <span style={{ color: "#f472b6" }}>❯</span>
                <span style={{ color: "#ffffff" }}>
                  {COMMANDS[activeIndex].cmd.substring(0, charsToShow)}
                  {transitionFrame < typeDuration + (fps * 0.5) && (
                    <span style={{
                      width: "10px",
                      height: "20px",
                      backgroundColor: "rgba(255,255,255,0.7)",
                      display: "inline-block",
                      marginLeft: "4px",
                      verticalAlign: "middle"
                    }} />
                  )}
                </span>
              </div>

              {/* Output */}
              <div style={{ color: "#d4d4d4", marginTop: "8px", paddingLeft: "24px", opacity: outputOpacity }}>
                {COMMANDS[activeIndex].output}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
