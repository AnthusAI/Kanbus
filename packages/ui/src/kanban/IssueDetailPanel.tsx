import React, { useEffect, useId, useRef, type ReactNode } from "react";
import type { KanbanIssue } from "./types";
import { IssueIdFormatProvider, useIssueIdPresentation, type IssueIdFormatter } from "./issue-id-format";

export interface IssueDetailField { label: string; value: ReactNode }
export interface IssueDetailPanelProps {
  issue: KanbanIssue;
  onClose: () => void;
  fields?: readonly IssueDetailField[];
  children?: ReactNode;
  className?: string;
  formatIssueId?: IssueIdFormatter;
}

/** A transport-free detail surface. Hosts supply display fields or editing content. */
export function IssueDetailPanel({ formatIssueId, ...panelProps }: IssueDetailPanelProps) {
  return <IssueIdFormatProvider formatIssueId={formatIssueId}><IssueDetailPanelContent {...panelProps} /></IssueIdFormatProvider>;
}

function IssueDetailPanelContent({ issue, onClose, fields = [], children, className = "" }: Omit<IssueDetailPanelProps, "formatIssueId">) {
  const issueIdPresentation = useIssueIdPresentation()(issue, (identifier) => identifier);
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    heading.current?.focus();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, [issue.id]);
  return <section className={`kb-issue-detail ${className}`} role="region" aria-label={`${issue.title} details`}
    onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    <div className="kb-detail-heading"><div><p className="kb-detail-id" data-issue-id-format={issueIdPresentation.formatAttribute}>{issueIdPresentation.text}</p>
      <h2 id={headingId} ref={heading} tabIndex={-1}>{issue.title}</h2></div>
      <button type="button" className="kb-detail-close" aria-label="Close issue details" onClick={onClose}>Close</button>
    </div>
    {issue.description && <p className="kb-detail-description">{issue.description}</p>}
    {fields.length > 0 && <dl className="kb-detail-fields">{fields.map(field => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>}
    {children}
  </section>;
}
