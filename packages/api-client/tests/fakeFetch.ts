import type { KanbusFetch } from "../src/index.js";

export interface RecordedRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

export function createFakeFetch(
  status: number,
  responseBody: unknown,
): { fetch: KanbusFetch; requests: RecordedRequest[] } {
  const requests: RecordedRequest[] = [];
  const fetchImplementation: KanbusFetch = async (input, init) => {
    requests.push({
      url: input,
      method: init?.method ?? "GET",
      headers: { ...((init?.headers as Record<string, string>) ?? {}) },
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    });
    const text = responseBody === undefined ? "" : JSON.stringify(responseBody);
    return new Response(text, { status, headers: { "content-type": "application/json" } });
  };
  return { fetch: fetchImplementation, requests };
}
