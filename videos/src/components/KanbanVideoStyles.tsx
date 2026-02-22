import React from "react";

const styles = `
.kanban-video {
  --slate-2: #f1f5f9;
  --slate-4: #cbd5e1;
  --slate-5: #94a3b8;
  --slate-6: #64748b;
  --slate-11: #0f172a;
  --gray-3: #e2e8f0;
  --gray-10: #64748b;
  --gray-12: #0f172a;
  --text-foreground: #0f172a;
  --text-muted: #64748b;
  --text-selected: #2563eb;
  --card: #f8fafc;
  --card-muted: #e2e8f0;
  --column: #e2e8f0;
  --scrollbar-thumb: #cbd5e1;
  --scrollbar-track: transparent;
  font-family: "IBM Plex Sans", "Inter", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
}

.kanban-video .flex { display: flex; }
.kanban-video .inline-flex { display: inline-flex; }
.kanban-video .grid { display: grid; }
.kanban-video .flex-col { flex-direction: column; }
.kanban-video .items-center { align-items: center; }
.kanban-video .justify-between { justify-content: space-between; }
.kanban-video .justify-end { justify-content: flex-end; }
.kanban-video .gap-0 { gap: 0; }
.kanban-video .gap-1 { gap: 4px; }
.kanban-video .gap-2 { gap: 8px; }
.kanban-video .p-3 { padding: 12px; }
.kanban-video .px-2 { padding-left: 8px; padding-right: 8px; }
.kanban-video .px-3 { padding-left: 12px; padding-right: 12px; }
.kanban-video .pt-2 { padding-top: 8px; }
.kanban-video .pr-1 { padding-right: 4px; }
.kanban-video .mb-0 { margin-bottom: 0; }
.kanban-video .mt-1 { margin-top: 4px; }
.kanban-video .-m-3 { margin: -12px; }
.kanban-video .h-7 { height: 28px; }
.kanban-video .w-4 { width: 16px; }
.kanban-video .h-4 { height: 16px; }
.kanban-video .w-full { width: 100%; }
.kanban-video .min-w-0 { min-width: 0; }
.kanban-video .min-h-0 { min-height: 0; }
.kanban-video .flex-1 { flex: 1 1 0%; }
.kanban-video .overflow-hidden { overflow: hidden; }
.kanban-video .overflow-y-auto { overflow-y: auto; }
.kanban-video .relative { position: relative; }
.kanban-video .cursor-pointer { cursor: default; }
.kanban-video .rounded-xl { border-radius: 12px; }
.kanban-video .bg-card { background: var(--card); }
.kanban-video .bg-card-muted { background: var(--card-muted); }
.kanban-video .text-xs { font-size: 12px; }
.kanban-video .text-base { font-size: 16px; }
.kanban-video .font-medium { font-weight: 500; }
.kanban-video .font-semibold { font-weight: 600; }
.kanban-video .uppercase { text-transform: uppercase; }
.kanban-video .tracking-wider { letter-spacing: 0.08em; }
.kanban-video .text-muted { color: var(--text-muted); }
.kanban-video .text-foreground { color: var(--text-foreground); }
.kanban-video .text-selected { color: var(--text-selected); }
.kanban-video .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kanban-video .shrink-0 { flex-shrink: 0; }
.kanban-video .opacity-60 { opacity: 0.6; }
.kanban-video .transition-opacity { transition: opacity 0.2s ease; }
.kanban-video .w-\\[calc\\(100%\\+1\\.5rem\\)\\] { width: calc(100% + 1.5rem); }

.kb-grid {
  display: flex;
  align-items: stretch;
  overflow-x: hidden;
  padding-bottom: 0;
  min-height: 100%;
}

.kb-column {
  background: transparent;
  border-radius: 12px;
  flex: 1 0 260px;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.kb-column-header {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.kb-column-scroll {
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
}

.issue-card {
  --issue-accent-foreground: var(--text-foreground);
  --issue-accent-light: var(--slate-4);
  --issue-accent-muted-light: var(--slate-2);
  --issue-accent-dark: var(--slate-11);
  --issue-accent-muted-dark: var(--slate-6);
  --issue-accent: var(--issue-accent-light);
  --issue-accent-muted: var(--issue-accent-muted-light);
  --issue-priority-bg-light: var(--slate-5);
  --issue-priority-bg-dark: var(--slate-6);
  --issue-priority-bg: var(--issue-priority-bg-light);
  border-radius: 12px;
  background: var(--card);
  display: grid;
  cursor: default;
  overflow: hidden;
  position: relative;
}

.issue-accent-bar {
  background: var(--issue-accent);
}

.issue-accent-icon {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  color: var(--issue-accent-foreground);
}

.issue-accent-id {
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.18em;
  color: var(--issue-accent-foreground);
}

.issue-accent-priority {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-foreground);
  background: var(--issue-priority-bg);
  border-radius: 999px;
  padding: 2px 8px;
  text-align: right;
  white-space: nowrap;
}
`;

export const KanbanVideoStyles: React.FC = () => {
  return <style>{styles}</style>;
};
