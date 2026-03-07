import React from "react";

interface WikiPageTreeProps {
  pages: string[];
  selectedPath: string | null;
  onSelectPath: (path: string) => void;
  onCreate: () => void;
  onRename: (path: string) => void;
  onDelete: (path: string) => void;
}

export function WikiPageTree({
  pages,
  selectedPath,
  onSelectPath,
  onCreate,
  onRename,
  onDelete
}: WikiPageTreeProps) {
  const canModify = Boolean(selectedPath);

  return (
    <div className="wiki-tree">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
          Pages
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-full bg-[var(--column)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted"
            onClick={onCreate}
          >
            New
          </button>
          <button
            type="button"
            className="rounded-full bg-[var(--column)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted"
            onClick={() => selectedPath && onRename(selectedPath)}
            disabled={!canModify}
          >
            Rename
          </button>
          <button
            type="button"
            className="rounded-full bg-[var(--column)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted"
            onClick={() => selectedPath && onDelete(selectedPath)}
            disabled={!canModify}
          >
            Delete
          </button>
        </div>
      </div>
      <div className="wiki-tree-list">
        {pages.map((path) => (
          <button
            key={path}
            type="button"
            className={`text-left rounded-lg px-3 py-2 text-sm transition-colors ${
              selectedPath === path ? "bg-[var(--background)] text-foreground" : "bg-transparent text-foreground"
            }`}
            onClick={() => onSelectPath(path)}
          >
            {path}
          </button>
        ))}
        {pages.length === 0 ? (
          <div className="wiki-empty-state">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
              Empty wiki
            </div>
            <div>Create your first page to get started.</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
