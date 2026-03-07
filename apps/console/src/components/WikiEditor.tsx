import React from "react";

interface WikiEditorProps {
  path: string | null;
  draftContent: string;
  isDirty: boolean;
  isSaving: boolean;
  onChange: (content: string) => void;
  onSave: () => void;
  onReset: () => void;
  hideHeader?: boolean;
}

export function WikiEditor({
  path,
  draftContent,
  isDirty,
  isSaving,
  onChange,
  onSave,
  onReset,
  hideHeader
}: WikiEditorProps) {
  return (
    <div className="wiki-editor h-full border-none rounded-none p-0 flex flex-col bg-transparent">
      {!hideHeader && (
        <div className="flex items-center justify-between gap-2 p-3 pb-0">
          <div className="flex flex-col">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
              Editor
            </div>
            <div className="text-sm text-foreground truncate max-w-[420px]">
              {path ?? "No page selected"}
            </div>
          </div>
        </div>
      )}
      <div className={`wiki-toolbar px-3 ${hideHeader ? "pt-3" : "pt-1"} pb-2 bg-[var(--background)] flex justify-between`}>
        <div className="text-xs text-muted font-medium py-1">
          {isDirty ? "Unsaved changes" : "Saved"}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-lg bg-[var(--column)] px-3 py-1 text-xs font-semibold uppercase tracking-wider text-foreground disabled:opacity-50 transition-colors"
            onClick={onSave}
            disabled={!isDirty || isSaving || !path}
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
          <button
            type="button"
            className="rounded-lg bg-[var(--column)] px-3 py-1 text-xs font-semibold uppercase tracking-wider text-muted hover:text-foreground disabled:opacity-50 transition-colors"
            onClick={onReset}
            disabled={!isDirty || !path}
          >
            Discard
          </button>
        </div>
      </div>
      <textarea
        className="flex-1 w-full p-4 bg-transparent border-none resize-none focus:outline-none font-mono text-sm leading-relaxed"
        value={draftContent}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Write markdown..."
      />
    </div>
  );
}
