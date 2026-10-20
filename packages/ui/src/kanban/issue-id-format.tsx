import React, { createContext, useContext, type ReactNode } from "react";
import type { KanbanIssue } from "./types";

/** Host hook that returns the exact text to show for an issue identifier. */
export type IssueIdFormatter = (issue: KanbanIssue) => string;

const IssueIdFormatContext = createContext<IssueIdFormatter | undefined>(undefined);

export interface IssueIdFormatProviderProps {
  formatIssueId?: IssueIdFormatter;
  children?: ReactNode;
}

/** Provide a host issue identifier formatter once for every board surface beneath it. */
export function IssueIdFormatProvider({ formatIssueId, children }: IssueIdFormatProviderProps) {
  if (!formatIssueId) {
    return <>{children}</>;
  }
  return <IssueIdFormatContext.Provider value={formatIssueId}>{children}</IssueIdFormatContext.Provider>;
}

export interface IssueIdPresentation {
  text: string;
  formatAttribute: "host" | undefined;
}

/** Resolve the displayed identifier text, preferring the host formatter over the supplied default. */
export function useIssueIdPresentation(): (
  issue: Pick<KanbanIssue, "id">,
  defaultText: (identifier: string) => string
) => IssueIdPresentation {
  const hostFormatter = useContext(IssueIdFormatContext);
  return (issue, defaultText) => {
    if (hostFormatter) {
      return { text: hostFormatter(issue as KanbanIssue), formatAttribute: "host" };
    }
    return { text: defaultText(issue.id), formatAttribute: undefined };
  };
}
