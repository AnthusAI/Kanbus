import * as React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "../remotion-shim";

export function PolicyDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stage1End = fps * 2;
  const stage2End = fps * 4;

  const policyOpacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });
  const policyY = interpolate(frame, [0, 10], [20, 0], { extrapolateRight: "clamp" });

  const cmdOpacity = interpolate(frame, [stage1End, stage1End + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const cmdString = "kanbus update task-123 --status in_progress";
  const cmdChars = Math.floor(interpolate(frame, [stage1End + 10, stage1End + fps], [0, cmdString.length], { extrapolateRight: "clamp" }));

  const errorOpacity = interpolate(frame, [stage2End, stage2End + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <div style={{
      position: "absolute",
      display: "flex",
      flexDirection: "row",
      gap: "32px",
      justifyContent: "center",
      alignItems: "center",
      padding: "32px",
      height: "500px",
      ...(style || { inset: 0 })
    }}>

      {/* Policy File */}
      <div style={{
        flex: 1,
        width: "100%",
        maxWidth: "448px",
        backgroundColor: "var(--card)",
        borderRadius: "12px",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
        border: "1px solid var(--border)",
        opacity: policyOpacity,
        transform: `translateY(${policyY}px)`
      }}>
        <div style={{
          backgroundColor: "var(--card-muted)",
          padding: "8px 16px",
          borderBottom: "1px solid rgba(0,0,0,0.5)",
          fontSize: "12px",
          color: "#4ade80",
          fontFamily: "monospace",
          display: "flex",
          alignItems: "center"
        }}>
          <span style={{ marginRight: "8px" }}>require-assignee.policy</span>
        </div>
        <div style={{ padding: "24px", height: "100%", display: "flex", alignItems: "center" }}>
          <pre style={{
            fontSize: "14px",
            fontFamily: "monospace",
            color: "#d4d4d4",
            lineHeight: "1.625",
            whiteSpace: "pre-wrap"
          }}>
            <span style={{ color: "#c084fc" }}>Feature:</span> Tasks require assignee{'\n\n'}
            <span style={{ color: "#60a5fa" }}>  Scenario:</span> Task must have assignee to start{'\n'}
            <span style={{ color: "#facc15" }}>    Given</span> the issue type is <span style={{ color: "#86efac" }}>"task"</span>{'\n'}
            <span style={{ color: "#facc15" }}>    When</span> transitioning to <span style={{ color: "#86efac" }}>"in_progress"</span>{'\n'}
            <span style={{ color: "#facc15" }}>    Then</span> the issue must have field <span style={{ color: "#86efac" }}>"assignee"</span>
          </pre>
        </div>
      </div>

      {/* Terminal Interaction */}
      <div style={{
        flex: 1,
        width: "100%",
        maxWidth: "448px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: "16px"
      }}>
        <div style={{
          width: "100%",
          backgroundColor: "var(--card)",
          borderRadius: "12px",
          overflow: "hidden",
          fontFamily: "monospace",
          fontSize: "18px",
          border: "1px solid var(--border)",
          opacity: cmdOpacity
        }}>
          <div style={{
            padding: "16px",
            display: "flex",
            alignItems: "center",
            color: "#4ade80"
          }}>
            <span style={{ color: "#60a5fa", marginRight: "8px" }}>~</span>
            <span style={{ color: "#f472b6", marginRight: "8px" }}>❯</span>
            <span style={{ color: "#ffffff", fontSize: "14px" }}>
              {cmdString.substring(0, Math.max(0, cmdChars))}
              <span style={{
                width: "8px",
                height: "16px",
                backgroundColor: "rgba(255,255,255,0.7)",
                display: "inline-block",
                marginLeft: "4px",
                verticalAlign: "middle"
              }} />
            </span>
          </div>

          <div style={{
            padding: "0 16px 16px",
            color: "#f87171",
            fontSize: "12px",
            opacity: errorOpacity
          }}>
            <div>Error: policy violation in require-assignee.policy</div>
            <div style={{ color: "var(--text-foreground)", marginLeft: "8px", marginTop: "4px" }}>Scenario: Task must have assignee to start</div>
            <div style={{ color: "var(--text-foreground)", marginLeft: "8px" }}>Failed: Then the issue must have field "assignee"</div>
            <div style={{
              color: "#ffffff",
              marginLeft: "8px",
              marginTop: "4px",
              borderLeft: "2px solid #ef4444",
              paddingLeft: "8px"
            }}>issue does not have field "assignee" set</div>
          </div>
        </div>
      </div>
    </div>
  );
}
