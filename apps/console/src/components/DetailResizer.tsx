import type { Dispatch, RefObject, SetStateAction } from "react";

type DetailResizerProps = {
  layoutFrameRef: RefObject<HTMLDivElement>;
  detailWidth: number;
  detailMaximized: boolean;
  setDetailWidth: Dispatch<SetStateAction<number>>;
  setDetailMaximized: Dispatch<SetStateAction<boolean>>;
  setIsResizing: Dispatch<SetStateAction<boolean>>;
};

export function DetailResizer({
  layoutFrameRef,
  detailWidth,
  detailMaximized,
  setDetailWidth,
  setDetailMaximized,
  setIsResizing,
}: DetailResizerProps) {
  return (
    <div
      className="detail-resizer h-full w-2 min-w-2 lg:w-3 lg:min-w-3 xl:w-4 xl:min-w-4 flex items-center justify-center cursor-col-resize pointer-events-auto"
      role="separator"
      onMouseDown={(event) => {
        const frame = layoutFrameRef.current;
        if (!frame) {
          return;
        }
        event.preventDefault();
        setIsResizing(true);
        const rect = frame.getBoundingClientRect();
        const effectiveWidth = detailMaximized ? 100 : detailWidth;
        if (detailMaximized) {
          setDetailWidth(100);
          setDetailMaximized(false);
        }
        const startX = event.clientX;
        const startWidth = effectiveWidth;
        const handleMove = (moveEvent: MouseEvent) => {
          const delta = moveEvent.clientX - startX;
          const pixelWidth = (startWidth / 100) * rect.width - delta;
          const clampedPixels = Math.max(320, Math.min(rect.width, pixelWidth));
          const clamped = (clampedPixels / rect.width) * 100;
          setDetailWidth(clamped);
        };
        const handleUp = () => {
          window.removeEventListener("mousemove", handleMove);
          window.removeEventListener("mouseup", handleUp);
          setIsResizing(false);
        };
        window.addEventListener("mousemove", handleMove);
        window.addEventListener("mouseup", handleUp);
      }}
      onTouchStart={(event) => {
        const frame = layoutFrameRef.current;
        if (!frame) {
          return;
        }
        const touch = event.touches[0];
        if (!touch) {
          return;
        }
        setIsResizing(true);
        const rect = frame.getBoundingClientRect();
        const effectiveWidth = detailMaximized ? 100 : detailWidth;
        if (detailMaximized) {
          setDetailWidth(100);
          setDetailMaximized(false);
        }
        const startX = touch.clientX;
        const startWidth = effectiveWidth;
        const handleMove = (moveEvent: TouchEvent) => {
          const moveTouch = moveEvent.touches[0];
          if (!moveTouch) {
            return;
          }
          const delta = moveTouch.clientX - startX;
          const pixelWidth = (startWidth / 100) * rect.width - delta;
          const clampedPixels = Math.max(320, Math.min(rect.width, pixelWidth));
          const clamped = (clampedPixels / rect.width) * 100;
          setDetailWidth(clamped);
        };
        const handleUp = () => {
          window.removeEventListener("touchmove", handleMove);
          window.removeEventListener("touchend", handleUp);
          setIsResizing(false);
        };
        window.addEventListener("touchmove", handleMove);
        window.addEventListener("touchend", handleUp);
      }}
    >
      <span className="h-5 w-1 rounded-full bg-[var(--gray-5)]" />
    </div>
  );
}
