import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  createWikiPage,
  deleteWikiPage,
  fetchWikiPage,
  fetchWikiPages,
  renameWikiPage,
  renderWikiPage,
  updateWikiPage
} from "../api/client";
import { WikiEditor } from "./WikiEditor";
import { WikiPreview } from "./WikiPreview";
import { WikiHeader } from "./WikiHeader";
import { WikiDirectoryListing } from "./WikiDirectoryListing";
import { resolveWikiRoute } from "../utils/wikiRouting";

const WIKI_EDIT_SPLIT_STORAGE_KEY = "kanbus.console.wikiEditSplitPercent";
const WIKI_EDIT_SPLIT_MIN = 25;
const WIKI_EDIT_SPLIT_MAX = 75;
const WIKI_EDIT_SPLIT_DEFAULT = 50;

function loadStoredWikiEditSplit(): number {
  if (typeof window === "undefined") return WIKI_EDIT_SPLIT_DEFAULT;
  const stored = window.localStorage.getItem(WIKI_EDIT_SPLIT_STORAGE_KEY);
  const parsed = stored ? Number.parseFloat(stored) : NaN;
  if (Number.isFinite(parsed) && parsed >= WIKI_EDIT_SPLIT_MIN && parsed <= WIKI_EDIT_SPLIT_MAX) {
    return parsed;
  }
  return WIKI_EDIT_SPLIT_DEFAULT;
}

interface WikiPanelProps {
  apiBase: string;
  isActive: boolean;
  onDirtyChange: (dirty: boolean) => void;
  initialRoutePath: string;
  onRouteChange: (path: string) => void;
}

export function WikiPanel({ apiBase, isActive, onDirtyChange, initialRoutePath, onRouteChange }: WikiPanelProps) {
  const [pages, setPages] = useState<string[]>([]);
  
  const [history, setHistory] = useState<string[]>(() => [initialRoutePath || ""]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const currentRoute = history[historyIndex] ?? "";
  
  // View mode
  const [viewMode, setViewMode] = useState<"read" | "edit">("read");

  // File state
  const [savedContent, setSavedContent] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [renderedMarkdown, setRenderedMarkdown] = useState("");
  
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isLoadingPages, setIsLoadingPages] = useState(false);
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editPaneRevealed, setEditPaneRevealed] = useState(false);
  const [exitingToRead, setExitingToRead] = useState(false);
  const [editPaneWidthPercent, setEditPaneWidthPercent] = useState(loadStoredWikiEditSplit);
  const [isResizing, setIsResizing] = useState(false);
  
  const autoRenderTimerRef = useRef<number | null>(null);
  const wikiSplitContainerRef = useRef<HTMLDivElement>(null);

  const isDirty = useMemo(() => draftContent !== savedContent, [draftContent, savedContent]);

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(() => {
    if (!isActive) {
      return;
    }
    void refreshPages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive]);

  const routeResult = useMemo(() => resolveWikiRoute(pages, currentRoute), [pages, currentRoute]);
  const isFile = routeResult.type === "file";
  const activePath = isFile ? routeResult.path : null;

  useEffect(() => {
    const norm = (s: string) => s.replace(/^\/+/, "").replace(/\/+$/, "");
    const normalized = norm(initialRoutePath ?? "");
    const current = norm(currentRoute);
    if (normalized === current) return;
    const idx = history.findIndex((h) => norm(h) === normalized);
    if (idx >= 0) {
      setHistoryIndex(idx);
    } else {
      const newHistory = [...history.slice(0, historyIndex + 1), normalized];
      setHistory(newHistory);
      setHistoryIndex(newHistory.length - 1);
    }
  }, [initialRoutePath]);

  useEffect(() => {
    if (isFile && activePath) {
      setIsLoadingFile(true);
      setSavedContent("");
      setDraftContent("");
      setRenderedMarkdown("");
      setRenderError(null);
      loadFile(activePath).finally(() => setIsLoadingFile(false));
    } else {
      setIsLoadingFile(false);
      setSavedContent("");
      setDraftContent("");
      setRenderedMarkdown("");
      setRenderError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePath, isFile]);

  function navigate(route: string) {
    if (isDirty) {
      const proceed = window.confirm("You have unsaved changes. Leave without saving?");
      if (!proceed) return;
    }
    const normalized = route.replace(/^\/+/, "").replace(/\/+$/, "");
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push(normalized);
    setHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);
    setViewMode("read");
    setError(null);
    onRouteChange(normalized);
  }

  function goBack() {
    if (historyIndex > 0) {
      if (isDirty) {
        const proceed = window.confirm("You have unsaved changes. Leave without saving?");
        if (!proceed) return;
      }
      const nextIndex = historyIndex - 1;
      setHistoryIndex(nextIndex);
      setViewMode("read");
      setError(null);
      onRouteChange(history[nextIndex] ?? "");
    }
  }

  function goForward() {
    if (historyIndex < history.length - 1) {
      if (isDirty) {
        const proceed = window.confirm("You have unsaved changes. Leave without saving?");
        if (!proceed) return;
      }
      const nextIndex = historyIndex + 1;
      setHistoryIndex(nextIndex);
      setViewMode("read");
      setError(null);
      onRouteChange(history[nextIndex] ?? "");
    }
  }

  async function refreshPages(): Promise<string[]> {
    setIsLoadingPages(true);
    setError(null);
    try {
      const result = await fetchWikiPages(apiBase);
      setPages(result.pages);
      return result.pages;
    } catch (err) {
      setError((err as Error).message);
      return [];
    } finally {
      setIsLoadingPages(false);
    }
  }

  function wikiShouldAutoRender() {
    return isActive && isFile && activePath && viewMode === "edit";
  }

  useEffect(() => {
    if (!wikiShouldAutoRender()) {
      return;
    }
    if (autoRenderTimerRef.current != null) {
      window.clearTimeout(autoRenderTimerRef.current);
      autoRenderTimerRef.current = null;
    }
    const timer = window.setTimeout(() => {
      autoRenderTimerRef.current = null;
      void handleRender();
    }, 800);
    autoRenderTimerRef.current = timer;
    return () => {
      window.clearTimeout(timer);
      if (autoRenderTimerRef.current === timer) {
        autoRenderTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftContent, activePath, isActive, viewMode]);

  useEffect(() => {
    if (isActive && isFile && activePath && (viewMode === "read" || (viewMode === "edit" && !isDirty))) {
      void handleRender();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePath, isActive, isDirty, viewMode, isFile]);

  useEffect(() => {
    if (!isActive || !isDirty) {
      return;
    }
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isActive, isDirty]);

  useEffect(() => {
    if (viewMode === "edit") {
      const id = requestAnimationFrame(() => setEditPaneRevealed(true));
      return () => cancelAnimationFrame(id);
    }
    setEditPaneRevealed(false);
  }, [viewMode]);

  useEffect(() => {
    window.localStorage.setItem(WIKI_EDIT_SPLIT_STORAGE_KEY, String(editPaneWidthPercent));
  }, [editPaneWidthPercent]);

  async function loadFile(path: string) {
    try {
      const page = await fetchWikiPage(apiBase, path);
      setSavedContent(page.content);
      setDraftContent(page.content);
      setRenderError(null);
      // We don't render here directly, the useEffect handles it
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleCreate() {
    const defaultPrefix = currentRoute ? `${currentRoute}/` : "";
    const path = window.prompt("Enter new page path (relative to root, ends with .md):", `${defaultPrefix}new_page.md`);
    if (!path) {
      return;
    }
    setError(null);
    try {
      await createWikiPage(apiBase, { path, content: "# New page\n" });
      await refreshPages();
      navigate(path);
      setViewMode("edit");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleRename() {
    if (!activePath) return;
    const next = window.prompt("Rename page to:", activePath);
    if (!next || next === activePath) {
      return;
    }
    if (isDirty) {
      const proceed = window.confirm("Unsaved changes will be lost. Continue?");
      if (!proceed) {
        return;
      }
    }
    setError(null);
    try {
      await renameWikiPage(apiBase, { from_path: activePath, to_path: next, overwrite: false });
      await refreshPages();
      navigate(next);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleDelete() {
    if (!activePath) return;
    const proceed = window.confirm(`Delete page "${activePath}"?`);
    if (!proceed) {
      return;
    }
    setError(null);
    try {
      const optimisticRemaining = pages.filter((candidate) => candidate !== activePath);
      await deleteWikiPage(apiBase, activePath);
      const refreshedPages = await refreshPages();
      const mergedCandidates = new Set<string>([...optimisticRemaining, ...refreshedPages]);
      const remainingPages = Array.from(mergedCandidates)
        .filter((candidate) => candidate !== activePath)
        .sort((a, b) => a.localeCompare(b));
      const nextPath = remainingPages[0] ?? "";
      const normalized = nextPath.replace(/^\/+/, "").replace(/\/+$/, "");
      const newHistory = history.slice(0, historyIndex + 1);
      newHistory.push(normalized);
      setHistory(newHistory);
      setHistoryIndex(newHistory.length - 1);
      setViewMode("read");
      onRouteChange(normalized);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleSave() {
    if (!activePath) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      await updateWikiPage(apiBase, { path: activePath, content: draftContent });
      setSavedContent(draftContent);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsSaving(false);
    }
  }

  function handleReset() {
    setDraftContent(savedContent);
    setRenderError(null);
  }

  async function handleRender() {
    if (!activePath) {
      return;
    }
    setIsRendering(true);
    setRenderError(null);
    try {
      const payload =
        draftContent !== savedContent
          ? { path: activePath, content: draftContent }
          : { path: activePath };
      const rendered = await renderWikiPage(apiBase, payload);
      setRenderedMarkdown(rendered.rendered_markdown);
    } catch (err) {
      setRenderError((err as Error).message);
    } finally {
      setIsRendering(false);
    }
  }

  return (
    <div className="wiki-panel flex flex-col h-full gap-4">
      <WikiHeader
        currentRoute={currentRoute}
        canGoBack={historyIndex > 0}
        canGoForward={historyIndex < history.length - 1}
        onGoBack={goBack}
        onGoForward={goForward}
        onNavigate={navigate}
        viewMode={viewMode}
        onChangeViewMode={(mode) => {
          if (mode === "read" && isDirty) {
            const proceed = window.confirm("You have unsaved changes. Discard and switch to read mode?");
            if (!proceed) return;
            handleReset();
          }
          if (mode === "read" && viewMode === "edit") {
            setViewMode("read");
            setExitingToRead(true);
            setEditPaneRevealed(false);
            return;
          }
          setViewMode(mode);
        }}
        isFile={isFile}
        onCreatePage={handleCreate}
        onRename={handleRename}
        onDelete={handleDelete}
      />
      
      {error ? <div className="wiki-error">{error}</div> : null}

      <div className="flex-1 overflow-hidden">
        {routeResult.type === "directory" ? (
          <WikiDirectoryListing
            path={routeResult.path}
            entries={routeResult.entries}
            onNavigate={navigate}
          />
        ) : routeResult.type === "file" ? (
          isLoadingFile ? (
            <div className="h-full flex items-center justify-center bg-[var(--card)] rounded-xl">
              <div className="loading-overlay-card flex flex-col items-center gap-3">
                <span className="loading-spinner" aria-hidden="true" />
                <span>Loading page...</span>
              </div>
            </div>
          ) : viewMode === "read" && !exitingToRead ? (
            <div className="h-full bg-[var(--card)] rounded-xl overflow-hidden">
              <WikiPreview
                path={activePath}
                renderedMarkdown={renderedMarkdown}
                renderError={renderError}
                isRendering={isRendering}
                onRender={handleRender}
                onNavigateToPage={navigate}
                hideHeader
              />
            </div>
          ) : (
            <div
              ref={wikiSplitContainerRef}
              className={`wiki-split-container flex h-full overflow-hidden gap-0${isResizing ? " is-resizing" : ""}`}
            >
              <div
                className="wiki-edit-pane flex flex-col flex-shrink-0 bg-[var(--card)] rounded-xl overflow-hidden min-w-0"
                style={{
                  width: editPaneRevealed ? `${editPaneWidthPercent}%` : "0%",
                  transition: "width var(--layout-transition) ease-out"
                }}
                onTransitionEnd={(e) => {
                  if (e.propertyName === "width" && exitingToRead) {
                    setExitingToRead(false);
                  }
                }}
              >
                <WikiEditor
                  path={activePath}
                  draftContent={draftContent}
                  isDirty={isDirty}
                  isSaving={isSaving}
                  onChange={setDraftContent}
                  onSave={handleSave}
                  onReset={handleReset}
                  hideHeader
                />
              </div>
              <div
                className="detail-resizer h-full w-2 min-w-2 lg:w-3 lg:min-w-3 xl:w-4 xl:min-w-4 flex items-center justify-center cursor-col-resize pointer-events-auto flex-shrink-0"
                role="separator"
                aria-label="Resize edit and preview panes"
                onMouseDown={(e) => {
                  const container = wikiSplitContainerRef.current;
                  if (!container) return;
                  e.preventDefault();
                  setIsResizing(true);
                  const rect = container.getBoundingClientRect();
                  const startX = e.clientX;
                  const startWidth = editPaneWidthPercent;
                  const handleMove = (moveEvent: MouseEvent) => {
                    const delta = moveEvent.clientX - startX;
                    const pixelWidth = (startWidth / 100) * rect.width + delta;
                    const minPx = rect.width * (WIKI_EDIT_SPLIT_MIN / 100);
                    const maxPx = rect.width * (WIKI_EDIT_SPLIT_MAX / 100);
                    const clampedPx = Math.max(minPx, Math.min(maxPx, pixelWidth));
                    setEditPaneWidthPercent((clampedPx / rect.width) * 100);
                  };
                  const handleUp = () => {
                    window.removeEventListener("mousemove", handleMove);
                    window.removeEventListener("mouseup", handleUp);
                    setIsResizing(false);
                  };
                  window.addEventListener("mousemove", handleMove);
                  window.addEventListener("mouseup", handleUp);
                }}
                onTouchStart={(e) => {
                  const container = wikiSplitContainerRef.current;
                  if (!container) return;
                  const touch = e.touches[0];
                  if (!touch) return;
                  setIsResizing(true);
                  const rect = container.getBoundingClientRect();
                  const startX = touch.clientX;
                  const startWidth = editPaneWidthPercent;
                  const handleMove = (moveEvent: TouchEvent) => {
                    const moveTouch = moveEvent.touches[0];
                    if (!moveTouch) return;
                    const delta = moveTouch.clientX - startX;
                    const pixelWidth = (startWidth / 100) * rect.width + delta;
                    const minPx = rect.width * (WIKI_EDIT_SPLIT_MIN / 100);
                    const maxPx = rect.width * (WIKI_EDIT_SPLIT_MAX / 100);
                    const clampedPx = Math.max(minPx, Math.min(maxPx, pixelWidth));
                    setEditPaneWidthPercent((clampedPx / rect.width) * 100);
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
              <div
                className="wiki-preview-pane flex-1 bg-[var(--card)] rounded-xl overflow-hidden min-w-0 transition-[width] ease-out"
                style={{ transitionDuration: "var(--layout-transition)" }}
              >
                <WikiPreview
                  path={activePath}
                  renderedMarkdown={renderedMarkdown}
                  renderError={renderError}
                  isRendering={isRendering}
                  onRender={handleRender}
                  onNavigateToPage={navigate}
                  hideHeader
                />
              </div>
            </div>
          )
        ) : (
          <div className="wiki-empty-state text-center mt-20">
            <h3 className="text-xl font-bold mb-2">Page Not Found</h3>
            <p>The path <code>{routeResult.path}</code> does not exist.</p>
          </div>
        )}
      </div>

      {isLoadingPages ? (
        <div className="loading-overlay">
          <div className="loading-overlay-card">Loading wiki...</div>
        </div>
      ) : null}
    </div>
  );
}
