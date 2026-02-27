import * as React from "react";
import { useRef, useState } from "react";

type HoverVideoPlayerProps = {
  src: string;
  poster?: string;
  className?: string;
};

export function HoverVideoPlayer({ src, poster, className = "" }: HoverVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const handleMouseEnter = () => {
    setIsPlaying(true);
    if (videoRef.current) {
      videoRef.current.play().catch(error => {
        // Autoplay may be prevented by browser
        console.error("Video playback failed", error);
      });
    }
  };

  const handleMouseLeave = () => {
    setIsPlaying(false);
    if (videoRef.current) {
      videoRef.current.pause();
      // Optional: reset the video to the beginning
      // videoRef.current.currentTime = 0;
    }
  };

  return (
    <div 
      className={`relative w-full h-full overflow-hidden bg-background ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Show poster image if not playing, or use the video element's built-in poster attribute. We will use the native video poster. */}
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        muted
        playsInline
        loop
        className="w-full h-full object-cover transition-opacity duration-300"
        style={{ opacity: isPlaying ? 1 : 0.8 }}
      />
      {/* Play Icon Indicator overlay (optional, but requested flat non-distracting) */}
      <div 
        className={`absolute inset-0 flex items-center justify-center pointer-events-none transition-opacity duration-300 ${isPlaying ? 'opacity-0' : 'opacity-100'}`}
      >
        <div className="w-12 h-12 rounded-full bg-card/80 flex items-center justify-center backdrop-blur-sm">
          <svg className="w-6 h-6 text-foreground ml-1" fill="currentColor" viewBox="0 0 24 24">
            <path d="M8 5v14l11-7z" />
          </svg>
        </div>
      </div>
    </div>
  );
}
