import { useEffect, useLayoutEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from "react";

export type DetailPanelLayout = {
  layoutFrameRef: RefObject<HTMLDivElement>;
  isResizing: boolean;
  setIsResizing: Dispatch<SetStateAction<boolean>>;
  detailMaximized: boolean;
  setDetailMaximized: Dispatch<SetStateAction<boolean>>;
  detailClosing: boolean;
  setDetailClosing: Dispatch<SetStateAction<boolean>>;
};

export function useDetailPanelLayout(detailWidth: number, isDetailOpen: boolean): DetailPanelLayout {
  const [isResizing, setIsResizing] = useState(false);
  const [detailMaximized, setDetailMaximized] = useState(false);
  const [detailClosing, setDetailClosing] = useState(false);
  const layoutFrameRef = useRef<HTMLDivElement | null>(null);
  const wasDetailOpenRef = useRef(false);

  useLayoutEffect(() => {
    const frame = layoutFrameRef.current;
    const shell = typeof document !== "undefined"
      ? (document.querySelector(".app-shell") as HTMLElement | null)
      : null;
    if (!frame) {
      return;
    }

    let raf = 0;
    const update = () => {
      const frameRect = frame.getBoundingClientRect();
      const viewportRight = document.documentElement.clientWidth || window.innerWidth;
      const outerPadding = Math.max(0, viewportRight - frameRect.right);
      const sidebar = frame.querySelector(".sidebar-column") as HTMLElement | null;
      const isCompact = window.matchMedia("(max-width: 768px)").matches;
      const defaultWidth =
        Number.parseFloat(getComputedStyle(frame).getPropertyValue("--sidebar-width"))
        || 360;
      const measuredWidth = sidebar?.getBoundingClientRect().width || 0;
      const compactWidth = Math.max(0, frameRect.width - outerPadding * 2);
      const sidebarWidth = isCompact ? compactWidth : (measuredWidth || defaultWidth);
      const gap = outerPadding;
      // Board push keeps a constant gap equal to frame padding.
      // Add a 1px overscan to guarantee the sidebar starts fully offscreen.
      const overscan = 1;
      const push = Math.ceil(sidebarWidth + outerPadding * 2) + overscan;
      frame.style.setProperty("--frame-padding", `${outerPadding}px`);
      frame.style.setProperty("--sidebar-gap", `${gap}px`);
      frame.style.setProperty("--sidebar-push", `${push}px`);
    };
    const schedule = () => {
      if (raf) {
        cancelAnimationFrame(raf);
      }
      raf = requestAnimationFrame(update);
    };

    schedule();
    const resizeObserver = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(schedule)
      : null;
    if (resizeObserver) {
      if (shell) {
        resizeObserver.observe(shell);
      }
      resizeObserver.observe(frame);
    }
    window.addEventListener("resize", schedule);
    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener("resize", schedule);
      if (raf) {
        cancelAnimationFrame(raf);
      }
    };
  }, []);

  useEffect(() => {
    if (!detailMaximized) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDetailMaximized(false);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [detailMaximized]);

  useEffect(() => {
    const wasOpen = wasDetailOpenRef.current;
    if (isDetailOpen) {
      setDetailClosing(false);
    } else if (wasOpen) {
      setDetailClosing(true);
    }
    wasDetailOpenRef.current = isDetailOpen;
  }, [isDetailOpen]);

  useLayoutEffect(() => {
    const layout = layoutFrameRef.current;
    if (!layout) {
      return;
    }
    const widthValue = detailMaximized ? 100 : detailWidth;
    layout.style.setProperty("--detail-width", `${widthValue}%`);
    layout.style.setProperty("--board-width", `calc(${100 - widthValue}% - 1rem)`);
  }, [detailWidth, detailMaximized]);

  return {
    layoutFrameRef,
    isResizing,
    setIsResizing,
    detailMaximized,
    setDetailMaximized,
    detailClosing,
    setDetailClosing,
  };
}
