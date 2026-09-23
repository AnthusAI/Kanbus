import React from "react";
import DOMPurify from "dompurify";

interface WikiPreviewProps {
  path: string | null;
  renderedHtml: string;
  renderError: string | null;
  isRendering: boolean;
  onRender: () => void;
  onNavigateToPage?: (path: string) => void;
  hideHeader?: boolean;
}

function resolveWikiPath(currentPath: string, href: string): string | null {
  const withoutHash = href.replace(/#.*$/, "").trim();
  if (!withoutHash.endsWith(".md")) return null;
  if (/^(https?:|mailto:)/i.test(withoutHash)) return null;
  const fromRoot = withoutHash.replace(/^\//, "");
  const currentDir = currentPath.includes("/") ? currentPath.replace(/\/[^/]*$/, "") : "";
  const base = currentDir ? `${currentDir}/` : "";
  const parts: string[] = [];
  for (const p of `${base}${fromRoot}`.split("/")) {
    if (p === "" || p === ".") continue;
    if (p === "..") {
      parts.pop();
      continue;
    }
    parts.push(p);
  }
  return parts.join("/");
}

function sanitizeWikiHtml(html: string): string {
  if (!html.trim()) return "";
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
}

export function WikiPreview({
  path,
  renderedHtml,
  renderError,
  isRendering,
  onRender,
  onNavigateToPage,
  hideHeader
}: WikiPreviewProps) {
  const previewHtml = sanitizeWikiHtml(renderedHtml);
  const hasPreview = Boolean(previewHtml.trim());

  function handlePreviewClick(event: React.MouseEvent<HTMLDivElement>) {
    const target = event.target;
    if (!(target instanceof HTMLAnchorElement)) return;
    const href = target.getAttribute("href");
    if (!href || !path || !onNavigateToPage) return;
    const resolved = resolveWikiPath(path, href);
    if (resolved) {
      event.preventDefault();
      onNavigateToPage(resolved);
    }
  }

  return (
    <div className="wiki-preview h-full">
      {!hideHeader && (
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-col">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
              Preview
            </div>
            <div className="text-sm text-foreground truncate max-w-[420px]">
              {path ?? "No page selected"}
            </div>
          </div>
          <button
            type="button"
            className="rounded-full bg-[var(--column)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted disabled:opacity-60"
            onClick={onRender}
            disabled={!path || isRendering}
          >
            {isRendering ? "Rendering..." : "Render"}
          </button>
        </div>
      )}
      {renderError ? (
        <div className="wiki-error" data-testid="wiki-render-error" role="alert">
          {renderError}
        </div>
      ) : null}
      {hasPreview ? (
        <div
          className="wiki-preview-html text-sm text-foreground max-w-none"
          dangerouslySetInnerHTML={{ __html: previewHtml }}
          onClick={handlePreviewClick}
          role="article"
        />
      ) : isRendering ? (
        <div className="flex flex-col items-center justify-center gap-3 py-8 text-sm text-muted">
          <span className="loading-spinner" aria-hidden="true" />
          <span>Rendering...</span>
        </div>
      ) : (
        <div className="text-sm text-muted">No preview yet</div>
      )}
    </div>
  );
}
