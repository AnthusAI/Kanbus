import type { IssuesSnapshot, Issue, IssueEventsResponse } from "../types/issues";

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

export type RealtimeBootstrap = {
  mode: string;
  region: string;
  iot_endpoint: string;
  iot_wss_url?: string;
  topic: string;
  account: string;
  project: string;
  client_id?: string;
  username?: string;
  password?: string;
};

type MqttModule = typeof import("mqtt");

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
      const logData: Record<string, unknown> = {
        type: notification.type,
        receivedAt: new Date().toISOString()
      };

      if (notification.type === "ui_control") {
        logData.action = notification.action.action;
      } else if ("issue_id" in notification) {
        logData.issueId = notification.issue_id;
      }

      console.info("[notifications] received", logData);
      console.info("[notifications] full payload", {
        notification,
        hasIssueData: "issue_data" in notification && Boolean(notification.issue_data)
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

export function subscribeToRealtimeFeed(
  apiBase: string,
  onNotification: (event: NotificationEvent) => void,
  onError?: (error: Event) => void
): () => void {
  let disposed = false;
  let mqttCleanup: (() => void) | null = null;
  let sseCleanup: (() => void) | null = null;

  const startSseFallback = (reason: string) => {
    if (disposed || sseCleanup) {
      return;
    }
    console.warn("[realtime] using SSE fallback", { reason });
    sseCleanup = subscribeToNotifications(apiBase, onNotification, onError);
  };

  const startMqtt = async (bootstrap: RealtimeBootstrap) => {
    if (disposed) {
      return;
    }
    const url = bootstrap.iot_wss_url ?? `wss://${bootstrap.iot_endpoint}/mqtt`;
    try {
      const mqtt = (await import("mqtt")) as MqttModule;
      const client = mqtt.connect(url, {
        clientId: bootstrap.client_id,
        username: bootstrap.username,
        password: bootstrap.password,
        clean: true,
        reconnectPeriod: 2000,
        connectTimeout: 10_000,
      });

      client.on("connect", () => {
        if (disposed) {
          client.end(true);
          return;
        }
        client.subscribe(bootstrap.topic, { qos: 0 }, (err) => {
          if (err) {
            console.warn("[realtime] mqtt subscribe failed", err);
            onError?.(new Event("mqtt-subscribe-error"));
            client.end(true);
            startSseFallback("mqtt-subscribe-error");
            return;
          }
          console.info("[realtime] mqtt subscribed", {
            topic: bootstrap.topic,
            endpoint: bootstrap.iot_endpoint,
            region: bootstrap.region,
          });
        });
      });

      client.on("message", (_topic, payload) => {
        try {
          const event = JSON.parse(payload.toString("utf-8")) as NotificationEvent;
          onNotification(event);
        } catch (error) {
          console.warn("[realtime] mqtt payload parse failed", error);
          onError?.(new Event("mqtt-parse-error"));
        }
      });

      client.on("error", (error) => {
        console.warn("[realtime] mqtt error", error);
        onError?.(new Event("mqtt-error"));
        client.end(true);
        startSseFallback("mqtt-error");
      });

      client.on("close", () => {
        if (!disposed && !sseCleanup) {
          startSseFallback("mqtt-closed");
        }
      });

      mqttCleanup = () => {
        client.end(true);
      };
    } catch (error) {
      console.warn("[realtime] mqtt transport unavailable", error);
      onError?.(new Event("mqtt-transport-unavailable"));
      startSseFallback("mqtt-transport-unavailable");
    }
  };

  fetchRealtimeBootstrap(apiBase)
    .then((bootstrap) => {
      if (disposed) {
        return;
      }
      console.info("[realtime] bootstrap", {
        mode: bootstrap.mode,
        region: bootstrap.region,
        topic: bootstrap.topic,
        account: bootstrap.account,
        project: bootstrap.project,
      });
      if (bootstrap.mode === "mqtt_iot") {
        void startMqtt(bootstrap);
        return;
      }
      startSseFallback(`unsupported-mode-${bootstrap.mode}`);
    })
    .catch((error) => {
      console.warn("[realtime] bootstrap failed", error);
      onError?.(new Event("bootstrap-error"));
      startSseFallback("bootstrap-error");
    });

  return () => {
    disposed = true;
    mqttCleanup?.();
    sseCleanup?.();
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

export async function fetchRealtimeBootstrap(
  apiBase: string
): Promise<RealtimeBootstrap> {
  const response = await fetch(`${apiBase}/realtime/bootstrap`);
  if (!response.ok) {
    throw new Error(`realtime bootstrap request failed: ${response.status}`);
  }
  return (await response.json()) as RealtimeBootstrap;
}
