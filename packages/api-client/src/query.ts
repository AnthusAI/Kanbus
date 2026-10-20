import type { KanbusIssueQuery } from "./types.js";

export type QueryParameters = Record<string, string>;

export function serializeIssueQuery(query: KanbusIssueQuery = {}): QueryParameters {
  const parameters: QueryParameters = {};
  const types = Array.isArray(query.type) ? query.type.join(",") : query.type;
  if (types !== undefined) parameters.type = types;
  for (const name of ["status", "assignee", "label", "parent", "search", "sort", "cursor"] as const) {
    const value = query[name];
    if (value !== undefined) parameters[name] = value;
  }
  if (query.limit !== undefined) parameters.limit = String(query.limit);
  if (query.fields !== undefined && query.fields.length > 0) {
    parameters.fields = JSON.stringify(query.fields);
  }
  return parameters;
}

export function encodeQueryString(parameters: QueryParameters): string {
  const entries = Object.entries(parameters);
  if (entries.length === 0) return "";
  const search = new URLSearchParams(entries);
  return `?${search.toString()}`;
}
