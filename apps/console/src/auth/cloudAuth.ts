import type { AuthBootstrap } from "../api/client";

const AUTH_STORAGE_KEY = "kanbus.console.cloudAuth";
const PKCE_STORAGE_PREFIX = "kanbus.console.pkce.";

type StoredAuth = {
  id_token: string;
  access_token: string;
  expires_at: number;
};

export type CloudAuthResult = {
  mode: "none" | "cognito_pkce";
  headers: Record<string, string>;
  queryToken: string | null;
  forbiddenReason: string | null;
  bootstrap: AuthBootstrap;
};

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function parseJwtClaims(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length < 2) {
    return null;
  }
  try {
    const json = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function randomString(size = 64): string {
  const bytes = new Uint8Array(size);
  crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256Base64Url(value: string): Promise<string> {
  const encoder = new TextEncoder();
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(value));
  const bytes = new Uint8Array(digest);
  const base64 = btoa(String.fromCharCode(...bytes));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function readStoredAuth(): StoredAuth | null {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as StoredAuth;
    if (!parsed.id_token || !parsed.access_token || !parsed.expires_at) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeStoredAuth(auth: StoredAuth): void {
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
}

function clearStoredAuth(): void {
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}

function encodeState(returnTo: string): string {
  const payload = JSON.stringify({ returnTo });
  return btoa(payload).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeState(value: string): { returnTo: string } | null {
  try {
    const json = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
    const parsed = JSON.parse(json) as { returnTo?: string };
    if (!parsed.returnTo) {
      return null;
    }
    return { returnTo: parsed.returnTo };
  } catch {
    return null;
  }
}

async function redirectToHostedUi(bootstrap: AuthBootstrap, returnTo: string): Promise<never> {
  const domainUrl = bootstrap.cognito_domain_url;
  const clientId = bootstrap.cognito_client_id;
  const redirectUri = bootstrap.cognito_redirect_uri;
  if (!domainUrl || !clientId || !redirectUri) {
    throw new Error("missing cognito bootstrap values");
  }
  const verifier = randomString(64);
  const challenge = await sha256Base64Url(verifier);
  const state = encodeState(returnTo);
  window.sessionStorage.setItem(`${PKCE_STORAGE_PREFIX}${state}`, verifier);
  const authorizeUrl = new URL(`${domainUrl}/oauth2/authorize`);
  authorizeUrl.searchParams.set("response_type", "code");
  authorizeUrl.searchParams.set("client_id", clientId);
  authorizeUrl.searchParams.set("redirect_uri", redirectUri);
  authorizeUrl.searchParams.set("scope", "openid email profile");
  authorizeUrl.searchParams.set("code_challenge_method", "S256");
  authorizeUrl.searchParams.set("code_challenge", challenge);
  authorizeUrl.searchParams.set("state", state);
  window.location.assign(authorizeUrl.toString());
  throw new Error("redirecting");
}

async function exchangeCodeForTokens(
  bootstrap: AuthBootstrap,
  code: string,
  state: string
): Promise<{ returnTo: string; auth: StoredAuth }> {
  const domainUrl = bootstrap.cognito_domain_url;
  const clientId = bootstrap.cognito_client_id;
  const redirectUri = bootstrap.cognito_redirect_uri;
  if (!domainUrl || !clientId || !redirectUri) {
    throw new Error("missing cognito bootstrap values");
  }
  const verifierKey = `${PKCE_STORAGE_PREFIX}${state}`;
  const codeVerifier = window.sessionStorage.getItem(verifierKey);
  window.sessionStorage.removeItem(verifierKey);
  if (!codeVerifier) {
    throw new Error("missing pkce verifier");
  }
  const tokenUrl = `${domainUrl}/oauth2/token`;
  const body = new URLSearchParams();
  body.set("grant_type", "authorization_code");
  body.set("client_id", clientId);
  body.set("code", code);
  body.set("redirect_uri", redirectUri);
  body.set("code_verifier", codeVerifier);
  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
  if (!response.ok) {
    throw new Error(`token exchange failed: ${response.status}`);
  }
  const payload = (await response.json()) as {
    id_token: string;
    access_token: string;
    expires_in: number;
  };
  const decodedState = decodeState(state);
  if (!decodedState) {
    throw new Error("invalid oauth state");
  }
  return {
    returnTo: decodedState.returnTo,
    auth: {
      id_token: payload.id_token,
      access_token: payload.access_token,
      expires_at: nowSeconds() + payload.expires_in
    }
  };
}

function tenantFromBasePath(basePath: string): { account: string; project: string } | null {
  const parts = basePath.split("/").filter(Boolean);
  if (parts.length < 2) {
    return null;
  }
  return { account: parts[0], project: parts[1] };
}

function validateTenantClaims(
  bootstrap: AuthBootstrap,
  idToken: string,
  basePath: string
): string | null {
  const tenant = tenantFromBasePath(basePath);
  if (!tenant) {
    return null;
  }
  const claims = parseJwtClaims(idToken);
  if (!claims) {
    return "unable to parse JWT claims";
  }
  const accountKey = bootstrap.tenant_account_claim_key ?? "custom:account";
  const projectKey = bootstrap.tenant_project_claim_key ?? "custom:project";
  const claimAccount = String(claims[accountKey] ?? "");
  const claimProject = String(claims[projectKey] ?? "");
  if (claimAccount !== tenant.account || claimProject !== tenant.project) {
    return `tenant claim mismatch (${claimAccount}/${claimProject})`;
  }
  return null;
}

export async function ensureCloudAuth(
  bootstrap: AuthBootstrap,
  currentBasePath: string
): Promise<CloudAuthResult> {
  if (bootstrap.mode !== "cognito_pkce") {
    clearStoredAuth();
    return {
      mode: "none",
      headers: {},
      queryToken: null,
      forbiddenReason: null,
      bootstrap
    };
  }

  const url = new URL(window.location.href);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (code && state) {
    const exchanged = await exchangeCodeForTokens(bootstrap, code, state);
    writeStoredAuth(exchanged.auth);
    const currentUrl = `${window.location.pathname}${window.location.search}`;
    if (exchanged.returnTo !== currentUrl) {
      window.location.assign(exchanged.returnTo);
      throw new Error("redirecting");
    }
    window.history.replaceState({}, "", exchanged.returnTo);
    return {
      mode: "cognito_pkce",
      headers: { Authorization: `Bearer ${exchanged.auth.id_token}` },
      queryToken: exchanged.auth.id_token,
      forbiddenReason: validateTenantClaims(bootstrap, exchanged.auth.id_token, exchanged.returnTo),
      bootstrap
    };
  }

  const stored = readStoredAuth();
  if (!stored || stored.expires_at <= nowSeconds() + 30) {
    await redirectToHostedUi(
      bootstrap,
      `${window.location.pathname}${window.location.search}${window.location.hash}`
    );
  }

  return {
    mode: "cognito_pkce",
    headers: { Authorization: `Bearer ${stored!.id_token}` },
    queryToken: stored!.id_token,
    forbiddenReason: validateTenantClaims(bootstrap, stored!.id_token, currentBasePath),
    bootstrap
  };
}

export function logoutCloudAuth(bootstrap: AuthBootstrap): void {
  clearStoredAuth();
  const domainUrl = bootstrap.cognito_domain_url;
  const clientId = bootstrap.cognito_client_id;
  const logoutUri = bootstrap.cognito_logout_uri ?? bootstrap.cognito_redirect_uri;
  if (!domainUrl || !clientId || !logoutUri) {
    window.location.reload();
    return;
  }
  const logoutUrl = new URL(`${domainUrl}/logout`);
  logoutUrl.searchParams.set("client_id", clientId);
  logoutUrl.searchParams.set("logout_uri", logoutUri);
  window.location.assign(logoutUrl.toString());
}
