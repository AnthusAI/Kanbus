import React from "react";

interface WikiPreviewProps {
  path: string | null;
  renderedMarkdown: string;
  renderError: string | null;
  isRendering: boolean;
  onRender: () => void;
}

export function WikiPreview({
  path,
  renderedMarkdown,
  renderError,
  isRendering,
  onRender
}: WikiPreviewProps) {
  return (
    <div className="wiki-preview">
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
      {renderError ? <div className="wiki-error">{renderError}</div> : null}
      <div className="issue-description-markdown text-sm text-foreground whitespace-pre-wrap">
        {renderedMarkdown || "No preview yet"}
      </div>
    </div>
  );
}
