import type { IssuesSnapshot, Issue, IssueEventsResponse } from "../types/issues";
import type {
  WikiCreateRequest,
  WikiCreateResponse,
  WikiDeleteResponse,
  WikiPageResponse,
  WikiPagesResponse,
  WikiRenameRequest,
  WikiRenameResponse,
  WikiRenderRequest,
  WikiRenderResponse,
  WikiUpdateRequest,
  WikiUpdateResponse
} from "../types/wiki";

export type UiControlAction =
  | { action: "clear_focus" }
  | { action: "set_view_mode"; mode: string }
  | { action: "set_search"; query: string }
  | { action: "maximize_detail" }
  | { action: "restore_detail" }
  | { action: "close_detail" }
  | { action: "toggle_settings" }
  | { action: "set_setting"; key: string; value: string }
  | { action: "collapse_column"; column_name: string }
  | { action: "expand_column"; column_name: string }
  | { action: "select_issue"; issue_id: string }
  | { action: "reload_page" };

export type NotificationEvent =
  | { type: "issue_created"; issue_id: string; issue_data: Issue }
  | { type: "issue_updated"; issue_id: string; fields_changed: string[]; issue_data: Issue }
  | { type: "issue_deleted"; issue_id: string }
  | { type: "issue_focused"; issue_id: string; user?: string; comment_id?: string }
  | { type: "ui_control"; action: UiControlAction };

export async function fetchSnapshot(apiBase: string): Promise<IssuesSnapshot> {
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

  source.onopen = () => {
    const now = Date.now();
    openCount += 1;
    lastMessageAt = null;
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
        lastMessageAt = Date.now();
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

  source.onopen = () => {};

  source.onmessage = (event) => {
    try {
      const notification = JSON.parse(event.data) as NotificationEvent;
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
    source.close();
  };
}

export async function fetchIssueEvents(
  apiBase: string,
  issueId: string,
  options?: { before?: string | null; limit?: number }
): Promise<IssueEventsResponse> {
  const params = new URLSearchParams();
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  if (options?.before) {
    params.set("before", options.before);
  }
  const query = params.toString();
  const url = query
    ? `${apiBase}/issues/${issueId}/events?${query}`
    : `${apiBase}/issues/${issueId}/events`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`issue events request failed: ${response.status}`);
  }
  return (await response.json()) as IssueEventsResponse;
}

export async function fetchWikiPages(apiBase: string): Promise<WikiPagesResponse> {
  const response = await fetch(`${apiBase}/wiki/pages`);
  if (!response.ok) {
    throw new Error(`wiki pages request failed: ${response.status}`);
  }
  return (await response.json()) as WikiPagesResponse;
}

export async function fetchWikiPage(apiBase: string, path: string): Promise<WikiPageResponse> {
  const url = `${apiBase}/wiki/page?path=${encodeURIComponent(path)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`wiki page request failed: ${response.status}`);
  }
  return (await response.json()) as WikiPageResponse;
}

export async function createWikiPage(
  apiBase: string,
  payload: WikiCreateRequest
): Promise<WikiCreateResponse> {
  const response = await fetch(`${apiBase}/wiki/page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`wiki create request failed: ${response.status}`);
  }
  return (await response.json()) as WikiCreateResponse;
}

export async function updateWikiPage(
  apiBase: string,
  payload: WikiUpdateRequest
): Promise<WikiUpdateResponse> {
  const response = await fetch(`${apiBase}/wiki/page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`wiki update request failed: ${response.status}`);
  }
  return (await response.json()) as WikiUpdateResponse;
}

export async function renameWikiPage(
  apiBase: string,
  payload: WikiRenameRequest
): Promise<WikiRenameResponse> {
  const response = await fetch(`${apiBase}/wiki/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`wiki rename request failed: ${response.status}`);
  }
  return (await response.json()) as WikiRenameResponse;
}

export async function deleteWikiPage(
  apiBase: string,
  path: string
): Promise<WikiDeleteResponse> {
  const url = `${apiBase}/wiki/page?path=${encodeURIComponent(path)}`;
  const response = await fetch(url, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`wiki delete request failed: ${response.status}`);
  }
  return (await response.json()) as WikiDeleteResponse;
}

export async function renderWikiPage(
  apiBase: string,
  payload: WikiRenderRequest
): Promise<WikiRenderResponse> {
  const response = await fetch(`${apiBase}/wiki/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    let message = `wiki render request failed: ${response.status}`;
    try {
      const body = (await response.json()) as { error?: string };
      if (typeof body?.error === "string" && body.error.length > 0) {
        message = body.error;
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return (await response.json()) as WikiRenderResponse;
}
