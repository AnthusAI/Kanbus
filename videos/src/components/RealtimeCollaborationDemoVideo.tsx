import * as React from "react";
import { useCurrentFrame, useVideoConfig } from "../remotion-shim";

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

const wrap01 = (t: number) => {
  const v = t % 1;
  return v < 0 ? v + 1 : v;
};

export function RealtimeCollaborationDemoVideo({ style }: { style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const dashOffset = -(t * 28);

  const pulse = (durationSec: number, phaseSec = 0) => wrap01((t + phaseSec) / durationSec);

  // Arrow segments (diagram space)
  const publishP = pulse(2.4, 0.0);
  const fanoutP = pulse(2.4, 0.8);
  const overlayWriteP = pulse(2.8, 0.2);
  const readBaseP = pulse(3.0, 1.0);

  const publishX = lerp(500, 540, publishP);
  const fanoutX = lerp(850, 900, fanoutP);
  const overlayWriteY = lerp(350, 530, overlayWriteP);
  const readBaseX = lerp(680, 900, readBaseP);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        boxSizing: "border-box",
        ...(style || {}),
      }}
    >
      <svg
        width="100%"
        height="100%"
        viewBox="0 0 1200 675"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ display: "block" }}
      >
        <defs>
          <marker id="rc-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-selected)" />
          </marker>
        </defs>

        {/* Boxes */}
        <rect x="70" y="140" width="430" height="210" rx="18" fill="var(--card)" stroke="var(--border)" strokeWidth="2" />
        <rect x="540" y="160" width="310" height="170" rx="18" fill="rgba(125, 211, 252, 0.06)" stroke="rgba(125, 211, 252, 0.65)" strokeWidth="2" />
        <rect x="900" y="140" width="240" height="210" rx="18" fill="var(--card)" stroke="var(--border)" strokeWidth="2" />
        <rect x="250" y="410" width="430" height="180" rx="18" fill="var(--card)" stroke="var(--border)" strokeWidth="2" />
        <rect x="680" y="430" width="250" height="120" rx="18" fill="var(--card)" stroke="var(--border)" strokeWidth="2" />
        <rect x="900" y="530" width="240" height="100" rx="18" fill="rgba(125, 211, 252, 0.06)" stroke="rgba(125, 211, 252, 0.65)" strokeWidth="2" />

        {/* Labels */}
        <text x="96" y="182" fill="var(--text-foreground)" fontFamily="&quot;Space Grotesk&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="18" fontWeight="800">
          Producers / Consumers
        </text>
        <text x="96" y="214" fill="var(--text-muted)" fontFamily="&quot;IBM Plex Sans&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="14" fontWeight="500">
          kbs / kanbus / kbsc / kanbus-console
        </text>

        <text x="566" y="202" fill="var(--text-foreground)" fontFamily="&quot;Space Grotesk&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="18" fontWeight="800">
          Broker
        </text>
        <text x="566" y="234" fill="var(--text-muted)" fontFamily="&quot;IBM Plex Sans&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="14" fontWeight="500">
          UDS (local) or MQTT (LAN/cloud)
        </text>

        <text x="926" y="182" fill="var(--text-foreground)" fontFamily="&quot;Space Grotesk&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="18" fontWeight="800">
          Overlay Cache
        </text>
        <text x="926" y="214" fill="var(--text-muted)" fontFamily="&quot;IBM Plex Sans&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="14" fontWeight="500">
          disposable, gitignored
        </text>

        <text x="276" y="452" fill="var(--text-foreground)" fontFamily="&quot;Space Grotesk&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="18" fontWeight="800">
          Git Working Tree (SSOT)
        </text>
        <text x="276" y="484" fill="var(--text-muted)" fontFamily="&quot;IBM Plex Sans&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="14" fontWeight="500">
          issue JSON + history
        </text>

        <text x="706" y="470" fill="var(--text-foreground)" fontFamily="&quot;Space Grotesk&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="18" fontWeight="800">
          Event JSON Log
        </text>
        <text x="706" y="502" fill="var(--text-muted)" fontFamily="&quot;IBM Plex Sans&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="14" fontWeight="500">
          append-only trail
        </text>

        <text x="926" y="572" fill="var(--text-foreground)" fontFamily="&quot;Space Grotesk&quot;, &quot;Inter&quot;, &quot;SF Pro Text&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif" fontSize="18" fontWeight="800">
          Read Path
        </text>
        <text x="926" y="604" fill="var(--text-muted)" fontFamily="&quot;IBM Plex Mono&quot;, &quot;SFMono-Regular&quot;, Menlo, Monaco, Consolas, &quot;Liberation Mono&quot;, &quot;Courier New&quot;, monospace" fontSize="14" fontWeight="800">
          base + overlay
        </text>

        {/* Arrows */}
        {/* publish envelope */}
        <path
          d="M 500 235 L 540 235"
          stroke="rgba(125, 211, 252, 0.7)"
          strokeWidth="2.5"
          strokeDasharray="8 8"
          strokeDashoffset={dashOffset}
          markerEnd="url(#rc-arrow)"
        />
        {/* fanout to watchers */}
        <path
          d="M 850 245 L 900 245"
          stroke="var(--text-selected)"
          strokeWidth="2.5"
          strokeDasharray="8 8"
          strokeDashoffset={dashOffset}
          markerEnd="url(#rc-arrow)"
        />
        {/* overlay write */}
        <path
          d="M 1020 350 L 1020 530"
          stroke="var(--text-selected)"
          strokeWidth="2.5"
          strokeDasharray="8 8"
          strokeDashoffset={dashOffset}
          markerEnd="url(#rc-arrow)"
        />
        {/* base + overlay -> read */}
        <path
          d="M 680 580 L 900 580"
          stroke="var(--text-selected)"
          strokeWidth="2.5"
          strokeDasharray="8 8"
          strokeDashoffset={dashOffset}
          markerEnd="url(#rc-arrow)"
        />

        {/* Pulses */}
        <circle cx={publishX} cy={235} r="6" fill="var(--text-selected)" opacity="0.95" />
        <circle cx={fanoutX} cy={245} r="6" fill="var(--text-selected)" opacity="0.95" />
        <circle cx={1020} cy={overlayWriteY} r="6" fill="var(--text-selected)" opacity="0.95" />
        <circle cx={readBaseX} cy={580} r="6" fill="var(--text-selected)" opacity="0.95" />

        {/* Callouts */}
        <g>
          <rect x="392" y="252" width="170" height="26" rx="999" fill="rgba(30, 41, 59, 0.85)" stroke="rgba(148, 163, 184, 0.35)" strokeWidth="1.5" />
          <text x="406" y="270" fill="var(--text-foreground)" fontFamily="&quot;IBM Plex Mono&quot;, &quot;SFMono-Regular&quot;, Menlo, Monaco, Consolas, &quot;Liberation Mono&quot;, &quot;Courier New&quot;, monospace" fontSize="12" fontWeight="800">
            best-effort publish
          </text>
        </g>
        <g>
          <rect x="820" y="262" width="200" height="26" rx="999" fill="rgba(30, 41, 59, 0.85)" stroke="rgba(148, 163, 184, 0.35)" strokeWidth="1.5" />
          <text x="834" y="280" fill="var(--text-foreground)" fontFamily="&quot;IBM Plex Mono&quot;, &quot;SFMono-Regular&quot;, Menlo, Monaco, Consolas, &quot;Liberation Mono&quot;, &quot;Courier New&quot;, monospace" fontSize="12" fontWeight="800">
            dedupe + ignore self
          </text>
        </g>
        <g>
          <rect x="282" y="600" width="240" height="26" rx="999" fill="rgba(30, 41, 59, 0.85)" stroke="rgba(148, 163, 184, 0.35)" strokeWidth="1.5" />
          <text x="296" y="618" fill="var(--text-foreground)" fontFamily="&quot;IBM Plex Mono&quot;, &quot;SFMono-Regular&quot;, Menlo, Monaco, Consolas, &quot;Liberation Mono&quot;, &quot;Courier New&quot;, monospace" fontSize="12" fontWeight="800">
            conflicts resolved by Git
          </text>
        </g>
      </svg>
    </div>
  );
}
