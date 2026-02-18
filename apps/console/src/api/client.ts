import type { IssuesSnapshot, Issue } from "../types/issues";

export type NotificationEvent =
  | { type: "issue_created"; issue_id: string; issue_data: Issue }
  | { type: "issue_updated"; issue_id: string; fields_changed: string[]; issue_data: Issue }
  | { type: "issue_deleted"; issue_id: string }
  | { type: "issue_focused"; issue_id: string; user?: string };

export async function fetchSnapshot(apiBase: string): Promise<IssuesSnapshot> {
  const startedAt = Date.now();
  const [configResponse, issuesResponse] = await Promise.all([
    fetch(`${apiBase}/config`),
    fetch(`${apiBase}/issues`)
  ]);

  if (!configResponse.ok) {
    throw new Error(`config request failed: ${configResponse.status}`);
  }

  if (!issuesResponse.ok) {
    throw new Error(`issues request failed: ${issuesResponse.status}`);
  }

  const config = (await configResponse.json()) as IssuesSnapshot["config"];
  const issues = (await issuesResponse.json()) as IssuesSnapshot["issues"];
  const finishedAt = Date.now();
  console.info("[snapshot] fetched", {
    durationMs: finishedAt - startedAt,
    finishedAt: new Date(finishedAt).toISOString()
  });

  return {
    config,
    issues,
    updated_at: new Date().toISOString()
  };
}

export function subscribeToSnapshots(
  apiBase: string,
  onSnapshot: (snapshot: IssuesSnapshot) => void,
  onError: (error: Event) => void
): () => void {
  const source = new EventSource(`${apiBase}/events`);
  let openCount = 0;
  let lastErrorAt: number | null = null;
  let lastMessageAt: number | null = null;

  console.info("[sse] connect", {
    url: `${apiBase}/events`,
    startedAt: new Date().toISOString()
  });

  source.onopen = () => {
    const now = Date.now();
    openCount += 1;
    console.info("[sse] open", {
      count: openCount,
      openedAt: new Date(now).toISOString(),
      sinceLastErrorMs: lastErrorAt ? now - lastErrorAt : null
    });
  };

  source.onmessage = (event) => {
    try {
      const snapshot = JSON.parse(event.data) as Partial<IssuesSnapshot> & {
        error?: string;
      };
      if (snapshot.error) {
        onError(new Event(snapshot.error));
        return;
      }
      if (snapshot.config && snapshot.issues) {
        const now = Date.now();
        lastMessageAt = now;
        console.info("[sse] message", {
          receivedAt: new Date(now).toISOString(),
          snapshotUpdatedAt: snapshot.updated_at ?? null,
          lastEventId: event.lastEventId || null
        });
        onSnapshot(snapshot as IssuesSnapshot);
        return;
      }
      onError(new Event("invalid-snapshot"));
    } catch {
      onError(new Event("parse-error"));
    }
  };

  source.onerror = (event) => {
    const now = Date.now();
    lastErrorAt = now;
    console.warn("[sse] error", {
      errorAt: new Date(now).toISOString(),
      sinceLastMessageMs: lastMessageAt ? now - lastMessageAt : null
    });
    onError(event);
  };

  return () => {
    source.close();
  };
}

export function subscribeToNotifications(
  apiBase: string,
  onNotification: (event: NotificationEvent) => void,
  onError?: (error: Event) => void
): () => void {
  const source = new EventSource(`${apiBase}/events/realtime`);

  console.info("[notifications] connect", {
    url: `${apiBase}/events/realtime`,
    startedAt: new Date().toISOString()
  });

  source.onopen = () => {
    console.info("[notifications] open", {
      openedAt: new Date().toISOString()
    });
  };

  source.onmessage = (event) => {
    try {
      const notification = JSON.parse(event.data) as NotificationEvent;
      console.info("[notifications] received", {
        type: notification.type,
        issueId: notification.issue_id,
        receivedAt: new Date().toISOString()
      });
      onNotification(notification);
    } catch (error) {
      console.error("[notifications] parse error", error);
      onError?.(new Event("parse-error"));
    }
  };

  source.onerror = (event) => {
    console.warn("[notifications] error", {
      errorAt: new Date().toISOString()
    });
    onError?.(event);
  };

  return () => {
    console.info("[notifications] disconnect");
    source.close();
  };
}
