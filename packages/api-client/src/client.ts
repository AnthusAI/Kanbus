import { KanbusApiError, type QueryBudgetCost } from "./errors.js";
import { encodeQueryString, serializeIssueQuery, type QueryParameters } from "./query.js";
import type {
  KanbusBoardConfiguration,
  KanbusBoardLifecycleOptions,
  KanbusBoardLifecycleResult,
  KanbusIssueDeletion,
  KanbusIssueEvents,
  KanbusIssueFields,
  KanbusIssuePage,
  KanbusIssuePatch,
  KanbusIssueQuery,
  KanbusIssueWithRevision,
  KanbusIssueWrite,
  KanbusProvisionOptions,
  KanbusRevisionWriteOptions,
  KanbusWriteOptions,
} from "./types.js";

export type KanbusFetch = (input: string, init?: RequestInit) => Promise<Response>;
export type KanbusHeaderValues = Record<string, string>;
export type KanbusHeaderProvider = () => Promise<KanbusHeaderValues> | KanbusHeaderValues;

export interface KanbusApiClientOptions {
  baseUrl: string;
  fetch?: KanbusFetch;
  headers?: KanbusHeaderProvider;
}

interface RequestSpecification {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  query?: QueryParameters;
  headers?: KanbusHeaderValues;
  body?: unknown;
}

interface ErrorBody {
  error?: string;
  message?: string;
  cost?: QueryBudgetCost;
}

function segment(value: string): string {
  return encodeURIComponent(value);
}

function writeHeaders(options: KanbusWriteOptions, ifMatch?: string): KanbusHeaderValues {
  const headers: KanbusHeaderValues = { "X-Operation-Id": options.operationId };
  if (ifMatch !== undefined) headers["If-Match"] = ifMatch;
  if (options.actor !== undefined) headers["X-Kanbus-Actor"] = options.actor;
  return headers;
}

export class KanbusApiTransport {
  private readonly baseUrl: string;
  private readonly fetchImplementation: KanbusFetch;
  private readonly headerProvider?: KanbusHeaderProvider;

  constructor(options: KanbusApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.fetchImplementation = options.fetch ?? ((input, init) => fetch(input, init));
    this.headerProvider = options.headers;
  }

  async send<ResponseBody>(specification: RequestSpecification): Promise<ResponseBody> {
    const hostHeaders = this.headerProvider ? await this.headerProvider() : {};
    const headers: KanbusHeaderValues = {
      accept: "application/json",
      ...hostHeaders,
      ...specification.headers,
    };
    const init: RequestInit = { method: specification.method, headers };
    if (specification.body !== undefined) {
      headers["content-type"] = "application/json";
      init.body = JSON.stringify(specification.body);
    }
    const url = `${this.baseUrl}${specification.path}${encodeQueryString(specification.query ?? {})}`;
    const response = await this.fetchImplementation(url, init);
    const text = await response.text();
    const parsed: unknown = text.length > 0 ? safeParse(text) : undefined;
    if (!response.ok) throw errorFromResponse(response.status, parsed);
    return parsed as ResponseBody;
  }
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function errorFromResponse(status: number, body: unknown): KanbusApiError {
  const details = (typeof body === "object" && body !== null ? body : {}) as ErrorBody;
  return new KanbusApiError({
    status,
    code: details.error ?? "unrecognized_error",
    message: details.message ?? `Request failed with status ${status}.`,
    cost: details.cost,
  });
}

export class BoardClient {
  private readonly prefix: string;

  constructor(
    private readonly transport: KanbusApiTransport,
    readonly tenant: string,
    readonly project: string,
  ) {
    this.prefix = `/${segment(tenant)}/${segment(project)}/api`;
  }

  getConfig(): Promise<KanbusBoardConfiguration> {
    return this.transport.send({ method: "GET", path: `${this.prefix}/config` });
  }

  provision(options: KanbusProvisionOptions): Promise<KanbusBoardConfiguration> {
    return this.transport.send({
      method: "PUT",
      path: `${this.prefix}/config`,
      headers: { "X-Operation-Id": options.operationId },
      body: options.configuration === undefined ? undefined : { configuration: options.configuration },
    });
  }

  listIssues(query: KanbusIssueQuery = {}): Promise<KanbusIssuePage> {
    return this.transport.send({
      method: "GET",
      path: `${this.prefix}/issues`,
      query: serializeIssueQuery(query),
    });
  }

  getIssue(id: string): Promise<KanbusIssueWithRevision> {
    return this.transport.send({ method: "GET", path: `${this.prefix}/issues/${segment(id)}` });
  }

  createIssue(input: KanbusIssueFields, options: KanbusWriteOptions): Promise<KanbusIssueWrite> {
    return this.transport.send({
      method: "POST",
      path: `${this.prefix}/issues`,
      headers: writeHeaders(options),
      body: input,
    });
  }

  updateIssue(
    id: string,
    patch: KanbusIssuePatch,
    options: KanbusRevisionWriteOptions,
  ): Promise<KanbusIssueWrite> {
    return this.transport.send({
      method: "PATCH",
      path: `${this.prefix}/issues/${segment(id)}`,
      headers: writeHeaders(options, options.ifMatch),
      body: patch,
    });
  }

  deleteIssue(id: string, options: KanbusRevisionWriteOptions): Promise<KanbusIssueDeletion> {
    return this.transport.send({
      method: "DELETE",
      path: `${this.prefix}/issues/${segment(id)}`,
      headers: writeHeaders(options, options.ifMatch),
    });
  }

  addComment(id: string, text: string, options: KanbusRevisionWriteOptions): Promise<KanbusIssueWrite> {
    return this.transport.send({
      method: "POST",
      path: `${this.prefix}/issues/${segment(id)}/comments`,
      headers: writeHeaders(options, options.ifMatch),
      body: { text },
    });
  }

  getEvents(id: string): Promise<KanbusIssueEvents> {
    return this.transport.send({
      method: "GET",
      path: `${this.prefix}/issues/${segment(id)}/events`,
    });
  }

  archive(options: KanbusBoardLifecycleOptions): Promise<KanbusBoardLifecycleResult> {
    return this.transport.send({
      method: "POST",
      path: `${this.prefix}/board/archive`,
      headers: writeHeaders(options),
    });
  }

  restore(options: KanbusBoardLifecycleOptions): Promise<KanbusBoardLifecycleResult> {
    return this.transport.send({
      method: "POST",
      path: `${this.prefix}/board/restore`,
      headers: writeHeaders(options),
    });
  }

  purge(options: KanbusBoardLifecycleOptions): Promise<KanbusBoardLifecycleResult> {
    return this.transport.send({
      method: "DELETE",
      path: `${this.prefix}/board`,
      headers: writeHeaders(options),
    });
  }
}

export class KanbusApiClient {
  private readonly transport: KanbusApiTransport;

  constructor(options: KanbusApiClientOptions) {
    this.transport = new KanbusApiTransport(options);
  }

  board(tenant: string, project: string): BoardClient {
    return new BoardClient(this.transport, tenant, project);
  }

  listAcrossBoards(
    tenant: string,
    projects: string[],
    query: KanbusIssueQuery = {},
  ): Promise<KanbusIssuePage> {
    return this.transport.send({
      method: "GET",
      path: `/${segment(tenant)}/api/issues`,
      query: { projects: projects.join(","), ...serializeIssueQuery(query) },
    });
  }
}

export function createKanbusApiClient(options: KanbusApiClientOptions): KanbusApiClient {
  return new KanbusApiClient(options);
}
