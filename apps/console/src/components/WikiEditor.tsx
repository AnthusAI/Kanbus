import React from "react";

interface WikiEditorProps {
  path: string | null;
  draftContent: string;
  isDirty: boolean;
  isSaving: boolean;
  onChange: (content: string) => void;
  onSave: () => void;
  onReset: () => void;
}

export function WikiEditor({
  path,
  draftContent,
  isDirty,
  isSaving,
  onChange,
  onSave,
  onReset
}: WikiEditorProps) {
  return (
    <div className="wiki-editor">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-col">
          <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-muted">
            Editor
          </div>
          <div className="text-sm text-foreground truncate max-w-[420px]">
            {path ?? "No page selected"}
          </div>
        </div>
        <div className="wiki-toolbar">
          <button
            type="button"
            className="rounded-full bg-[var(--column)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted disabled:opacity-60"
            onClick={onSave}
            disabled={!isDirty || isSaving || !path}
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
          <button
            type="button"
            className="rounded-full bg-[var(--column)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted disabled:opacity-60"
            onClick={onReset}
            disabled={!isDirty || !path}
          >
            Reset
          </button>
        </div>
      </div>
      <textarea
        value={draftContent}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Write markdown..."
      />
      {isDirty ? (
        <div className="text-xs text-muted">Unsaved changes</div>
      ) : (
        <div className="text-xs text-muted">Saved</div>
      )}
    </div>
  );
}
