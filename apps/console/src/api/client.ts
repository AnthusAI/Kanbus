import type { IssuesSnapshot } from "../types/issues";

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
        onSnapshot(snapshot as IssuesSnapshot);
        return;
      }
      onError(new Event("invalid-snapshot"));
    } catch {
      onError(new Event("parse-error"));
    }
  };

  source.onerror = (event) => {
    onError(event);
  };

  return () => {
    source.close();
  };
}
