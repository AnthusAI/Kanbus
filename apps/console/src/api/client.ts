import type { IssuesSnapshot, Issue, IssueEventsResponse } from "../types/issues";
import { SignatureV4 } from "@aws-sdk/signature-v4";
import { Sha256 } from "@aws-crypto/sha256-js";
import { HttpRequest } from "@aws-sdk/protocol-http";
import { formatUrl } from "@aws-sdk/util-format-url";
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
  | { type: "cloud_sync_completed"; account: string; project: string; sha: string; ref?: string | null }
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
  mqtt_custom_authorizer_name?: string;
  client_id?: string;
  username?: string;
  password?: string;
};

export type AuthBootstrap = {
  mode: string;
  cognito_domain_url?: string | null;
  cognito_client_id?: string | null;
  cognito_redirect_uri?: string | null;
  cognito_logout_uri?: string | null;
  cognito_issuer?: string | null;
  identity_pool_id?: string | null;
  tenant_account_claim_key?: string | null;
  tenant_project_claim_key?: string | null;
  account?: string | null;
  project?: string | null;
};

type MqttModule = typeof import("mqtt");
type SigV4Credentials = {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken: string;
  identityId: string;
};

type HeaderProvider = () => Promise<Record<string, string>> | Record<string, string>;
type QueryProvider = () => string | null;

let authHeaderProvider: HeaderProvider | null = null;
let authQueryProvider: QueryProvider | null = null;
let mqttTokenProvider: QueryProvider | null = null;

export function setAuthHeaderProvider(provider: HeaderProvider | null): void {
  authHeaderProvider = provider;
}

export function setAuthQueryProvider(provider: QueryProvider | null): void {
  authQueryProvider = provider;
}

export function setMqttTokenProvider(provider: QueryProvider | null): void {
  mqttTokenProvider = provider;
}

async function fetchWithAuth(input: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers ?? {});
  if (authHeaderProvider) {
    const provided = await authHeaderProvider();
    Object.entries(provided).forEach(([key, value]) => {
      if (value) {
        headers.set(key, value);
      }
    });
  }
  return fetch(input, {
    ...init,
    headers
  });
}

function withAuthQuery(url: string): string {
  const token = authQueryProvider?.();
  if (!token) {
    return url;
  }
  const u = new URL(url, window.location.origin);
  u.searchParams.set("access_token", token);
  return `${u.pathname}${u.search}`;
}

async function buildSignedIotWebsocketUrl(
  endpoint: string,
  region: string,
  credentials: SigV4Credentials
): Promise<string> {
  const request = new HttpRequest({
    protocol: "wss:",
    hostname: endpoint,
    method: "GET",
    path: "/mqtt",
    headers: {
      host: endpoint,
    },
  });
  const signer = new SignatureV4({
    service: "iotdevicegateway",
    region,
    sha256: Sha256,
    credentials: {
      accessKeyId: credentials.accessKeyId,
      secretAccessKey: credentials.secretAccessKey,
      sessionToken: credentials.sessionToken,
    },
  });
  const signed = await signer.presign(request, { expiresIn: 900 });
  return formatUrl(signed);
}

function loginProviderKeyFromIssuer(issuer: string): string | null {
  try {
    const url = new URL(issuer);
    return `${url.host}${url.pathname}`;
  } catch {
    return null;
  }
}

async function fetchCognitoIdentityCredentials(
  region: string,
  identityPoolId: string,
  loginProviderKey: string,
  idToken: string
): Promise<SigV4Credentials> {
  const endpoint = `https://cognito-identity.${region}.amazonaws.com/`;
  const commonHeaders = {
    "Content-Type": "application/x-amz-json-1.1",
  };
  const getIdResponse = await fetch(endpoint, {
    method: "POST",
    headers: {
      ...commonHeaders,
      "X-Amz-Target": "AWSCognitoIdentityService.GetId",
    },
    body: JSON.stringify({
      IdentityPoolId: identityPoolId,
      Logins: { [loginProviderKey]: idToken },
    }),
  });
  if (!getIdResponse.ok) {
    throw new Error(`cognito GetId failed: ${getIdResponse.status}`);
  }
  const getIdPayload = (await getIdResponse.json()) as { IdentityId?: string };
  const identityId = getIdPayload.IdentityId;
  if (!identityId) {
    throw new Error("cognito GetId response missing IdentityId");
  }

  const getCredentialsResponse = await fetch(endpoint, {
    method: "POST",
    headers: {
      ...commonHeaders,
      "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
    },
    body: JSON.stringify({
      IdentityId: identityId,
      Logins: { [loginProviderKey]: idToken },
    }),
  });
  if (!getCredentialsResponse.ok) {
    throw new Error(`cognito GetCredentialsForIdentity failed: ${getCredentialsResponse.status}`);
  }
  const getCredentialsPayload = (await getCredentialsResponse.json()) as {
    IdentityId?: string;
    Credentials?: {
      AccessKeyId?: string;
      SecretKey?: string;
      SessionToken?: string;
    };
  };
  const creds = getCredentialsPayload.Credentials;
  if (!creds?.AccessKeyId || !creds?.SecretKey || !creds?.SessionToken) {
    throw new Error("cognito credentials response missing key material");
  }
  return {
    accessKeyId: creds.AccessKeyId,
    secretAccessKey: creds.SecretKey,
    sessionToken: creds.SessionToken,
    identityId: getCredentialsPayload.IdentityId ?? identityId,
  };
}

export async function fetchSnapshot(apiBase: string): Promise<IssuesSnapshot> {
  const [configResponse, issuesResponse] = await Promise.all([
    fetchWithAuth(`${apiBase}/config`),
    fetchWithAuth(`${apiBase}/issues`)
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
  const source = new EventSource(withAuthQuery(`${apiBase}/events`));
  let openCount = 0;
  let lastErrorAt: number | null = null;
  let lastMessageAt: number | null = null;

  source.onopen = () => {
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
  const source = new EventSource(withAuthQuery(`${apiBase}/events/realtime`));

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
    const defaultUrl = bootstrap.iot_wss_url ?? `wss://${bootstrap.iot_endpoint}/mqtt`;
    try {
      const mqttToken = mqttTokenProvider?.();
      const useCustomAuthorizer = Boolean(
        bootstrap.mqtt_custom_authorizer_name
        && mqttToken
      );
      const authBootstrap = useCustomAuthorizer ? null : await fetchAuthBootstrap(apiBase);
      const loginProviderKey = authBootstrap?.cognito_issuer
        ? loginProviderKeyFromIssuer(authBootstrap.cognito_issuer)
        : null;
      const idToken = authQueryProvider?.();
      const sigv4Credentials = (
        authBootstrap?.identity_pool_id
        && loginProviderKey
        && idToken
        && authBootstrap.mode === "cognito_pkce"
      )
        ? await fetchCognitoIdentityCredentials(
          bootstrap.region,
          authBootstrap.identity_pool_id,
          loginProviderKey,
          idToken
        )
        : null;
      const signedUrl = useCustomAuthorizer
        ? defaultUrl
        : sigv4Credentials
          ? await buildSignedIotWebsocketUrl(
            bootstrap.iot_endpoint,
            bootstrap.region,
            sigv4Credentials
          )
          : defaultUrl;
      const cognitoClientId = sigv4Credentials
        ? `${sigv4Credentials.identityId}-${bootstrap.account}-${bootstrap.project}`.slice(0, 128)
        : undefined;
      const customAuthorizerName = bootstrap.mqtt_custom_authorizer_name;
      const username = (useCustomAuthorizer && customAuthorizerName)
        ? `?x-amz-customauthorizer-name=${encodeURIComponent(customAuthorizerName)}`
        : bootstrap.username;
      const password = useCustomAuthorizer
        ? mqttToken
        : bootstrap.password;
      console.info("[realtime] mqtt auth mode", {
        useCustomAuthorizer,
        hasMqttToken: Boolean(mqttToken),
        hasIdToken: Boolean(idToken),
        customAuthorizerName: customAuthorizerName ?? null,
      });

      const mqtt = (await import("mqtt")) as MqttModule & {
        default?: unknown;
      };
      const connectCandidate =
        (mqtt as { connect?: unknown }).connect
        ?? (mqtt.default as { connect?: unknown } | undefined)?.connect
        ?? mqtt.default;
      if (typeof connectCandidate !== "function") {
        throw new Error("mqtt module does not expose connect()");
      }
      const client = connectCandidate(signedUrl, {
        clientId: bootstrap.client_id ?? cognitoClientId,
        username,
        password,
        protocolVersion: 4,
        clean: true,
        reconnectPeriod: 2000,
        connectTimeout: 10_000,
      }) as {
        subscribe: (topic: string, options: { qos: number }, callback: (err?: Error | null) => void) => void;
        on: (event: string, callback: (...args: unknown[]) => void) => void;
        end: (force?: boolean) => void;
      };

      client.on("connect", () => {
        if (disposed) {
          client.end(true);
          return;
        }
        client.subscribe(bootstrap.topic, { qos: 0 }, (err?: Error | null) => {
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

      client.on("message", (_topic: unknown, payload: unknown) => {
        try {
          const raw = typeof payload === "string"
            ? payload
            : payload instanceof Uint8Array
              ? new TextDecoder().decode(payload)
              : String(payload);
          const event = JSON.parse(raw) as NotificationEvent;
          const logData: Record<string, unknown> = {
            type: event.type,
            receivedAt: new Date().toISOString()
          };
          if (event.type === "ui_control") {
            logData.action = event.action.action;
          } else if (event.type === "cloud_sync_completed") {
            logData.sha = event.sha;
            logData.account = event.account;
            logData.project = event.project;
            logData.ref = event.ref ?? null;
          } else if ("issue_id" in event) {
            logData.issueId = event.issue_id;
          }
          console.info("[notifications] received", logData);
          console.info("[notifications] full payload", {
            notification: event,
            hasIssueData: "issue_data" in event && Boolean(event.issue_data)
          });
          onNotification(event);
        } catch (error) {
          console.warn("[realtime] mqtt payload parse failed", error);
          onError?.(new Event("mqtt-parse-error"));
        }
      });

      client.on("error", (error: unknown) => {
        console.warn("[realtime] mqtt error", error);
        onError?.(new Event("mqtt-error"));
        client.end(true);
        startSseFallback("mqtt-error");
      });

      client.on("close", () => {
        console.warn("[realtime] mqtt close", { useCustomAuthorizer });
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
  const response = await fetchWithAuth(url);
  if (!response.ok) {
    throw new Error(`issue events request failed: ${response.status}`);
  }
  return (await response.json()) as IssueEventsResponse;
}

export async function fetchRealtimeBootstrap(
  apiBase: string
): Promise<RealtimeBootstrap> {
  const response = await fetchWithAuth(`${apiBase}/realtime/bootstrap`);
  if (!response.ok) {
    throw new Error(`realtime bootstrap request failed: ${response.status}`);
  }
  return (await response.json()) as RealtimeBootstrap;
}

export async function fetchAuthBootstrap(apiBase: string): Promise<AuthBootstrap> {
  const response = await fetch(`${apiBase}/auth/bootstrap`);
  if (!response.ok) {
    throw new Error(`auth bootstrap request failed: ${response.status}`);
  }
  return (await response.json()) as AuthBootstrap;
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
