import * as React from "react";
import { getVideoSrc } from "../lib/getVideoSrc";
import { getVideoById } from "../content/videos";

export default function VmlVideo() {
  const video = getVideoById("intro");
  if (!video) return null;

  return (
    <video
      controls
      preload="metadata"
      playsInline
      src={getVideoSrc(video.filename)}
      poster={video.poster ? getVideoSrc(video.poster) : undefined}
      style={{
        width: "100%",
        display: "block",
        borderRadius: "14px",
        background: "rgba(0, 0, 0, 0.75)",
      }}
    />
  );
}
