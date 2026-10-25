import { useCallback, useEffect, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { fetchNowIssues, fetchSnapshot, subscribeToSnapshots } from "../api/client";
import type { PanelMode } from "../types/console";
import type { Issue, IssuesSnapshot } from "../types/issues";

const SNAPSHOT_FALLBACK_INTERVAL_MS = 15_000;

export type SnapshotFeed = {
  snapshot: IssuesSnapshot | null;
  setSnapshot: Dispatch<SetStateAction<IssuesSnapshot | null>>;
  snapshotRef: MutableRefObject<IssuesSnapshot | null>;
  error: string | null;
  errorTime: number | null;
  loading: boolean;
  authReady: boolean;
  apiBase: string;
  refreshSnapshot: () => Promise<void>;
  startSnapshotFallback: () => void;
  stopSnapshotFallback: () => void;
  replaceIssueInSnapshot: (issueId: string, issue: Issue) => void;
  beginAuthentication: () => void;
  failLoading: (message: string, stampTime: boolean) => void;
  completeInitialLoad: (data: IssuesSnapshot) => void;
};

export function useSnapshotFeed(basePath: string | null, panelMode: PanelMode): SnapshotFeed {
  const [snapshot, setSnapshot] = useState<IssuesSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorTime, setErrorTime] = useState<number | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const snapshotRef = useRef<IssuesSnapshot | null>(null);
  const lastSnapshotSuccessAtRef = useRef<number>(Date.now());
  const snapshotFallbackTimerRef = useRef<number | null>(null);
  const snapshotFallbackRequestRef = useRef<Promise<void> | null>(null);
  const apiBase = basePath != null ? `${basePath}/api` : "";

  const refreshSnapshot = useCallback(() => {
    if (!apiBase) {
      return Promise.resolve();
    }
    if (snapshotFallbackRequestRef.current) {
      return snapshotFallbackRequestRef.current;
    }
    // This path is used when realtime delivery is unavailable. Rebuild the
    // backend snapshot from its Git checkout instead of reading stale memory.
    const request = fetchSnapshot(apiBase, { refresh: true })
      .then((data) => {
        lastSnapshotSuccessAtRef.current = Date.now();
        snapshotRef.current = data;
        setSnapshot(data);
        setError(null);
        setErrorTime(null);
      })
      .catch((err) => {
        console.warn("[snapshot] refresh failed", err);
        setError("Unable to reach the server. Showing stale data.");
        setErrorTime(Date.now());
      });
    snapshotFallbackRequestRef.current = request;
    void request.finally(() => {
      if (snapshotFallbackRequestRef.current === request) {
        snapshotFallbackRequestRef.current = null;
      }
    });
    return request;
  }, [apiBase]);

  const stopSnapshotFallback = useCallback(() => {
    if (snapshotFallbackTimerRef.current !== null) {
      window.clearInterval(snapshotFallbackTimerRef.current);
      snapshotFallbackTimerRef.current = null;
    }
  }, []);

  const startSnapshotFallback = useCallback(() => {
    if (!apiBase || snapshotFallbackTimerRef.current !== null) {
      return;
    }
    setError("Realtime updates unavailable. Refreshing from Git.");
    setErrorTime(Date.now());
    void refreshSnapshot();
    snapshotFallbackTimerRef.current = window.setInterval(() => {
      void refreshSnapshot();
    }, SNAPSHOT_FALLBACK_INTERVAL_MS);
  }, [apiBase, refreshSnapshot]);

  useEffect(() => stopSnapshotFallback, [stopSnapshotFallback]);

  useEffect(() => {
    const refreshHandle = window as Window & {
      __KANBUS_REFRESH_SNAPSHOT__?: () => Promise<void>;
    };
    refreshHandle.__KANBUS_REFRESH_SNAPSHOT__ = refreshSnapshot;
    return () => {
      delete refreshHandle.__KANBUS_REFRESH_SNAPSHOT__;
    };
  }, [refreshSnapshot]);

  useEffect(() => {
    if (panelMode !== "now" || !apiBase) {
      return;
    }
    fetchNowIssues(apiBase)
      .then((nowIssues) => {
        setSnapshot((previous) =>
          previous
            ? { ...previous, issues: nowIssues, updated_at: new Date().toISOString() }
            : previous
        );
      })
      .catch((err) => console.warn("[now] backfill failed", err));
  }, [panelMode, apiBase]);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  useEffect(() => {
    if (basePath == null || !authReady) {
      return;
    }
    const snapshotApiBase = `${basePath}/api`;
    const unsubscribe = subscribeToSnapshots(
      snapshotApiBase,
      (nextSnapshot) => {
        lastSnapshotSuccessAtRef.current = Date.now();
        snapshotRef.current = nextSnapshot;
        setSnapshot(nextSnapshot);
        setError(null);
        setErrorTime(null);
        stopSnapshotFallback();
      },
      () => {
        const staleMs = Date.now() - lastSnapshotSuccessAtRef.current;
        startSnapshotFallback();
        if (staleMs < SNAPSHOT_FALLBACK_INTERVAL_MS) {
          return;
        }
        setError("Unable to reach the server. Showing stale data.");
        setErrorTime(Date.now());
      }
    );
    return () => {
      unsubscribe();
      stopSnapshotFallback();
    };
  }, [basePath, authReady, startSnapshotFallback, stopSnapshotFallback]);

  const replaceIssueInSnapshot = useCallback((issueId: string, issue: Issue) => {
    setSnapshot((current) => current ? {
      ...current,
      issues: current.issues.map((existing) => existing.id === issueId ? issue : existing),
      updated_at: new Date().toISOString()
    } : current);
  }, []);

  const beginAuthentication = useCallback(() => {
    setAuthReady(false);
    setLoading(true);
  }, []);

  const failLoading = useCallback((message: string, stampTime: boolean) => {
    setError(message);
    if (stampTime) {
      setErrorTime(Date.now());
    }
    setLoading(false);
  }, []);

  const completeInitialLoad = useCallback((data: IssuesSnapshot) => {
    lastSnapshotSuccessAtRef.current = Date.now();
    setSnapshot(data);
    setError(null);
    setAuthReady(true);
    setLoading(false);
  }, []);

  return {
    snapshot,
    setSnapshot,
    snapshotRef,
    error,
    errorTime,
    loading,
    authReady,
    apiBase,
    refreshSnapshot,
    startSnapshotFallback,
    stopSnapshotFallback,
    replaceIssueInSnapshot,
    beginAuthentication,
    failLoading,
    completeInitialLoad,
  };
}
