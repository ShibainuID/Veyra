/**
 * The API error envelope `{"error": {"code", "message", "details"}}` and plain-language copy for
 * every documented code. Copy names the problem and the recovery.
 */

export type ErrorCode =
  | "IDENTITY_UNCONFIRMED"
  | "EVIDENCE_INCOMPLETE"
  | "APPROVAL_REQUIRED"
  | "APPROVAL_STALE"
  | "ACTION_EXPIRED"
  | "INSUFFICIENT_SANDBOX_FUNDS"
  | "DUPLICATE_EXECUTION"
  | "INVALID_STATE"
  | "FORBIDDEN_ROLE"
  | "UNAUTHENTICATED"
  | "NOT_FOUND"
  | "VALIDATION_FAILED"
  | "IDEMPOTENCY_KEY_REQUIRED"
  | "NETWORK_ERROR";

export const FALLBACK_ERROR_COPY = "Something went wrong. Try again.";

export const ERROR_COPY: Record<ErrorCode, string> = {
  IDENTITY_UNCONFIRMED: "Confirm this animal's identity before any financial action.",
  EVIDENCE_INCOMPLETE: "Some required evidence is missing.",
  APPROVAL_REQUIRED: "This action needs a manager's approval before it can run.",
  APPROVAL_STALE: "The details changed after approval. Review the new version.",
  ACTION_EXPIRED: "This approval window has closed. Prepare the action again.",
  INSUFFICIENT_SANDBOX_FUNDS: "The sandbox wallet doesn't hold enough for this payment.",
  DUPLICATE_EXECUTION: "This action has already run, so it was not run again.",
  INVALID_STATE: "This record changed since you opened it. Refresh to see where it stands.",
  FORBIDDEN_ROLE: "Your role can't do this. Switch to Manager to approve.",
  UNAUTHENTICATED: "Your session isn't recognised. Choose a role to continue.",
  NOT_FOUND: "That record isn't on this farm, or it was removed.",
  VALIDATION_FAILED: "Some values aren't valid. Check them and try again.",
  IDEMPOTENCY_KEY_REQUIRED: FALLBACK_ERROR_COPY,
  NETWORK_ERROR: "Can't reach the VEYRA service. Check the connection, then try again.",
};

export function errorCopy(code: string | null | undefined): string {
  if (code && code in ERROR_COPY) return ERROR_COPY[code as ErrorCode];
  return FALLBACK_ERROR_COPY;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Plain copy for this error, suitable for the interface. */
  get copy(): string {
    return errorCopy(this.code);
  }

  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }

  static fromEnvelope(status: number, body: unknown): ApiError {
    if (body && typeof body === "object" && "error" in body) {
      const err = (body as { error: unknown }).error;
      if (err && typeof err === "object") {
        const { code, message, details } = err as { code?: unknown; message?: unknown; details?: unknown };
        return new ApiError(
          status,
          typeof code === "string" ? code : "HTTP_ERROR",
          typeof message === "string" ? message : `Request failed with status ${status}.`,
          details && typeof details === "object" ? (details as Record<string, unknown>) : {},
        );
      }
    }
    return new ApiError(status, status === 404 ? "NOT_FOUND" : "HTTP_ERROR", `Request failed with status ${status}.`);
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    return ApiError.fromEnvelope(response.status, body);
  }

  static network(cause?: unknown): ApiError {
    const err = new ApiError(0, "NETWORK_ERROR", "The request did not reach the server.");
    if (cause !== undefined) (err as Error).cause = cause;
    return err;
  }
}

export function toApiError(error: unknown): ApiError | null {
  return error instanceof ApiError ? error : null;
}
