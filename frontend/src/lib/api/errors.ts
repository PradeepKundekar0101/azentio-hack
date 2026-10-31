/** The backend's error envelope: `{"error": {"code", "message", "details"}}`. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown;
  };
}

/** Error raised for any non-2xx API response. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const FALLBACK_MESSAGES: Record<number, string> = {
  401: "Your session has ended. Sign in again.",
  403: "You do not have access to this.",
  404: "Not found.",
  429: "Too many attempts. Wait a minute and try again.",
  500: "The server hit an error. Try again, and report it if it keeps happening.",
  502: "The server is not reachable. Check that the backend is running.",
  503: "The server is temporarily unavailable.",
  504: "The server did not respond in time.",
};

function readErrorBody(body: unknown): Partial<ApiErrorBody["error"]> {
  if (!body || typeof body !== "object" || !("error" in body)) return {};
  const inner = (body as { error: unknown }).error;
  if (!inner || typeof inner !== "object") return {};
  const { code, message, details } = inner as Record<string, unknown>;
  return {
    code: typeof code === "string" ? code : undefined,
    message: typeof message === "string" && message ? message : undefined,
    details: details ?? null,
  };
}

/** Builds an ApiError from a parsed error body and its Response. */
export function toApiError(body: unknown, response: Response): ApiError {
  const { code, message, details } = readErrorBody(body);
  return new ApiError(
    response.status,
    code ?? "error",
    message ?? FALLBACK_MESSAGES[response.status] ?? `Request failed (${response.status}).`,
    details ?? null,
  );
}

/**
 * Unwraps an openapi-fetch result: returns `data` or throws ApiError.
 *
 *   const session = unwrap(await api.GET("/api/v1/auth/me"));
 */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok && result.error === undefined) {
    return result.data as T;
  }
  throw toApiError(result.error, result.response);
}

/** A human-readable message for any thrown value. */
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) {
    return "Could not reach the server. Check your connection and that the backend is running.";
  }
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong.";
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
