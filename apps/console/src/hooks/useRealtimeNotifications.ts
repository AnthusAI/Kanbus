import { useEffect } from "react";
import { fetchSnapshot, subscribeToRealtimeFeed, type NotificationEvent, type UiControlAction } from "../api/client";
import type { SnapshotFeed } from "./useSnapshotFeed";

type RealtimeNotificationOptions = {
  basePath: string | null;
  feed: SnapshotFeed;
  onIssueFocused: (issueId: string, commentId: string | null) => void;
  onUiControlAction: (action: UiControlAction) => void;
};

export function useRealtimeNotifications({
  basePath,
  feed,
  onIssueFocused,
  onUiControlAction,
}: RealtimeNotificationOptions): void {
  const { authReady, snapshotRef, setSnapshot, startSnapshotFallback, stopSnapshotFallback } = feed;

  useEffect(() => {
    if (basePath == null || !authReady) {
      return;
    }
    const apiBase = `${basePath}/api`;
    const unsubscribe = subscribeToRealtimeFeed(
      apiBase,
      (event: NotificationEvent) => {
        switch (event.type) {
          case "issue_focused":
            onIssueFocused(event.issue_id, event.comment_id ?? null);
            break;
          case "issue_created":
          case "issue_updated":
            if (event.issue_data) {
              const current = snapshotRef.current;
              if (current) {
                const existing = current.issues.some((issue) => issue.id === event.issue_id);
                const updatedIssues = existing
                  ? current.issues.map((issue) =>
                    issue.id === event.issue_id ? event.issue_data : issue
                  )
                  : [...current.issues, event.issue_data];
                const nextSnapshot = {
                  ...current,
                  issues: updatedIssues,
                  updated_at: new Date().toISOString()
                };
                snapshotRef.current = nextSnapshot;
                setSnapshot(nextSnapshot);
                console.info("[notifications] applied issue update immediately", {
                  type: event.type,
                  issueId: event.issue_id
                });
                break;
              }
            }
            fetchSnapshot(apiBase).then(setSnapshot).catch(console.error);
            break;
          case "issue_deleted":
            {
              const current = snapshotRef.current;
              if (current) {
                const nextSnapshot = {
                  ...current,
                  issues: current.issues.filter((issue) => issue.id !== event.issue_id),
                  updated_at: new Date().toISOString()
                };
                snapshotRef.current = nextSnapshot;
                setSnapshot(nextSnapshot);
                console.info("[notifications] applied issue deletion immediately", {
                  issueId: event.issue_id
                });
              } else {
                fetchSnapshot(apiBase).then(setSnapshot).catch(console.error);
              }
            }
            break;
          case "ui_control":
            onUiControlAction(event.action);
            break;
        }
      },
      (error) => {
        console.warn("[notifications] connection error", error);
        startSnapshotFallback();
      }
    );

    return () => {
      unsubscribe();
      stopSnapshotFallback();
    };
  }, [basePath, authReady, startSnapshotFallback, stopSnapshotFallback]);
}
