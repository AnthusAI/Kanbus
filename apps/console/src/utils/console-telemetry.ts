type TelemetryLevel = "log" | "info" | "warn" | "error" | "debug";

type TelemetryPayload = {
  level: TelemetryLevel;
  message: string | null;
  args: unknown[];
  timestamp: string;
  url: string;
  session_id: string;
};

type TelemetryState = {
  installed: boolean;
  endpoint: string | null;
  sessionId: string;
};

const stateKey = "__kanbusConsoleTelemetryState";

function getTelemetryState(): TelemetryState {
  const existing = (window as typeof window & Record<string, unknown>)[stateKey] as
    | TelemetryState
    | undefined;
  if (existing) {
    return existing;
  }
  const sessionId = Math.random().toString(36).slice(2, 10);
  const nextState: TelemetryState = {
    installed: false,
    endpoint: null,
    sessionId
  };
  (window as typeof window & Record<string, unknown>)[stateKey] = nextState;
  return nextState;
}

function serializeConsoleArg(value: unknown): unknown {
  if (value == null) {
    return value;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      stack: value.stack ?? null
    };
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return String(value);
  }
}

function sendTelemetry(endpoint: string, payload: TelemetryPayload): void {
  const body = JSON.stringify(payload);
  if (navigator.sendBeacon) {
    navigator.sendBeacon(endpoint, body);
    return;
  }
  void fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body,
    keepalive: true
  });
}

function buildPayload(level: TelemetryLevel, args: unknown[]): TelemetryPayload {
  const message = typeof args[0] === "string" ? args[0] : null;
  return {
    level,
    message,
    args: args.map(serializeConsoleArg),
    timestamp: new Date().toISOString(),
    url: window.location.href,
    session_id: getTelemetryState().sessionId
  };
}

export function installConsoleTelemetry(apiBase: string): void {
  const state = getTelemetryState();
  if (state.installed && state.endpoint === `${apiBase}/telemetry/console`) {
    return;
  }
  state.installed = true;
  state.endpoint = `${apiBase}/telemetry/console`;

  const levels: TelemetryLevel[] = ["log", "info", "warn", "error", "debug"];
  for (const level of levels) {
    const original = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      original(...args);
      sendTelemetry(state.endpoint as string, buildPayload(level, args));
    };
  }

  window.addEventListener("error", (event) => {
    const payload = buildPayload("error", [
      event.message,
      {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
      }
    ]);
    sendTelemetry(state.endpoint as string, payload);
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason instanceof Error
      ? {
          name: event.reason.name,
          message: event.reason.message,
          stack: event.reason.stack ?? null
        }
      : serializeConsoleArg(event.reason);
    const payload = buildPayload("error", ["unhandledrejection", reason]);
    sendTelemetry(state.endpoint as string, payload);
  });
}
