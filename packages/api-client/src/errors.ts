export type KanbusApiErrorCode =
  | "forbidden"
  | "unauthorized"
  | "not_found"
  | "invalid_request"
  | "invalid_issue"
  | "invalid_configuration"
  | "configuration_invalid"
  | "configuration_missing"
  | "revision_required"
  | "revision_conflict"
  | "operation_conflict"
  | "unsupported_relation_mutation"
  | "query_budget_exceeded"
  | "board_exists"
  | "board_archived"
  | "board_not_archived"
  | "storage_unavailable"
  | "unrecognized_error";

export interface QueryBudgetCost {
  limit: string;
  consumed?: Record<string, number>;
  serialized_body_bytes?: number;
}

export interface KanbusApiErrorDetails {
  status: number;
  code: KanbusApiErrorCode | (string & {});
  message: string;
  cost?: QueryBudgetCost;
}

export class KanbusApiError extends Error {
  readonly status: number;
  readonly code: KanbusApiErrorCode | (string & {});
  readonly cost?: QueryBudgetCost;

  constructor(details: KanbusApiErrorDetails) {
    super(details.message);
    this.name = "KanbusApiError";
    this.status = details.status;
    this.code = details.code;
    this.cost = details.cost;
  }

  get isRevisionConflict(): boolean {
    return this.code === "revision_conflict";
  }
}
