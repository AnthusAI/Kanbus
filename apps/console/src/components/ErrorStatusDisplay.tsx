import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const paddedSecs = String(secs).padStart(2, "0");

  if (minutes === 0) {
    return `${secs}s`;
  }
  return `${minutes}m ${paddedSecs}s`;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true
  });
}

export function ErrorStatusDisplay({ errorTime }: { errorTime: number }) {
  const errorTimeRef = useRef(errorTime);
  const [duration, setDuration] = useState<string>(() => {
    const now = Date.now();
    const elapsedSeconds = Math.floor((now - errorTime) / 1000);
    return formatDuration(elapsedSeconds);
  });
  const [lastUpdated] = useState(() => formatTime(new Date(errorTime)));

  const durationRef = useRef<HTMLSpanElement>(null);
  const animationRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const updateTime = () => {
      const now = Date.now();
      const elapsedSeconds = Math.floor((now - errorTimeRef.current) / 1000);
      setDuration(formatDuration(elapsedSeconds));
    };

    // Update immediately and then every second
    updateTime();
    animationRef.current = setInterval(updateTime, 1000);

    return () => {
      if (animationRef.current) {
        clearInterval(animationRef.current);
      }
    };
  }, []);

  // Animate the duration text with GSAP when it changes
  useEffect(() => {
    if (!durationRef.current) {
      return;
    }

    // Smooth crossfade animation
    gsap.fromTo(
      durationRef.current,
      {
        opacity: 0.5
      },
      {
        opacity: 1,
        duration: 0.4,
        ease: "power2.out"
      }
    );
  }, [duration]);

  return (
    <div className="rounded-xl px-4 py-2 text-sm" style={{ background: 'var(--danger-bg)' }}>
      <div className="font-semibold flex flex-wrap items-center gap-x-2 gap-y-1" style={{ color: 'var(--danger-text)' }}>
        <span>Unable to reach the server</span>
        <span className="grow" />
        <span className="font-normal flex items-center gap-2">
          <span>Not updated for</span>
          <span
            ref={durationRef}
            className="font-mono font-semibold"
          >
            {duration}
          </span>
          <span>since</span>
          <span className="font-mono font-semibold">{lastUpdated}</span>
        </span>
      </div>
    </div>
  );
}
