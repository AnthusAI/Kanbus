import { useEffect } from "react";
import {
  fetchAuthBootstrap,
  fetchSnapshot,
  setAuthHeaderProvider,
  setAuthQueryProvider,
  setMqttTokenProvider,
} from "../api/client";
import { ensureCloudAuth } from "../auth/cloudAuth";
import { installConsoleTelemetry } from "../utils/console-telemetry";
import type { SnapshotFeed } from "./useSnapshotFeed";

export function useCloudAuth(basePath: string | null, feed: SnapshotFeed): void {
  const { beginAuthentication, failLoading, completeInitialLoad } = feed;

  useEffect(() => {
    let isMounted = true;
    beginAuthentication();
    if (basePath == null) {
      failLoading("URL must include /:account/:project", false);
      return () => {};
    }
    const apiBase = `${basePath}/api`;
    installConsoleTelemetry(apiBase);

    void (async () => {
      try {
        const bootstrap = await fetchAuthBootstrap(apiBase);
        if (!isMounted) {
          return;
        }
        const authResult = await ensureCloudAuth(bootstrap, basePath ?? "");
        if (!isMounted) {
          return;
        }
        setAuthHeaderProvider(() => authResult.headers);
        setAuthQueryProvider(() => authResult.queryToken);
        setMqttTokenProvider(() => authResult.mqttToken);
        if (authResult.forbiddenReason) {
          failLoading(`Forbidden: ${authResult.forbiddenReason}`, true);
          return;
        }
        const data = await fetchSnapshot(apiBase);
        if (!isMounted) {
          return;
        }
        completeInitialLoad(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to initialize auth";
        if (message === "redirecting") {
          return;
        }
        if (!isMounted) {
          return;
        }
        failLoading(message, true);
      }
    })();

    return () => {
      isMounted = false;
      setAuthHeaderProvider(null);
      setAuthQueryProvider(null);
      setMqttTokenProvider(null);
    };
  }, [basePath, beginAuthentication, failLoading, completeInitialLoad]);
}
