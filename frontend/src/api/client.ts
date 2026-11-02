/** Small fetch wrapper for the Cratekeeper API. */

export interface FieldError {
  /** Settings field the error belongs to, or null for the whole request. */
  field: string | null;
  loc: (string | number)[];
  message: string;
}

export class ApiError extends Error {
  override readonly name = "ApiError";
  readonly status: number;
  readonly detail: unknown;
  readonly fieldErrors: FieldError[];

  constructor(
    message: string,
    status: number,
    detail: unknown = null,
    fieldErrors: FieldError[] = [],
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

export function isApiError(error: unknown, status?: number): error is ApiError {
  return error instanceof ApiError && (status === undefined || error.status === status);
}

const LOCATION_PREFIXES = new Set(["body", "query", "path", "header", "cookie"]);

function fieldFromLoc(loc: (string | number)[]): string | null {
  const rest = LOCATION_PREFIXES.has(String(loc[0])) ? loc.slice(1) : loc;
  const first = rest[0];
  return typeof first === "string" ? first : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Turn a FastAPI `detail` (string or list of pydantic errors) into text and field errors. */
export function parseDetail(detail: unknown): {
  message: string | null;
  fieldErrors: FieldError[];
} {
  if (typeof detail === "string") {
    return { message: detail, fieldErrors: [] };
  }
  if (Array.isArray(detail)) {
    const fieldErrors: FieldError[] = detail.filter(isRecord).map((item) => {
      const loc = Array.isArray(item.loc)
        ? item.loc.filter(
            (p): p is string | number => typeof p === "string" || typeof p === "number",
          )
        : [];
      const message = typeof item.msg === "string" ? item.msg : "Invalid value";
      return { field: fieldFromLoc(loc), loc, message };
    });
    const message = fieldErrors
      .map((e) => (e.field ? `${e.field}: ${e.message}` : e.message))
      .join("; ");
    return { message: message || null, fieldErrors };
  }
  return { message: null, fieldErrors: [] };
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const fallback = `${response.status} ${response.statusText}`.trim();
  const text = await response.text().catch(() => "");
  let detail: unknown = null;
  let message: string | null = null;
  let fieldErrors: FieldError[] = [];
  if (text) {
    try {
      const body: unknown = JSON.parse(text);
      detail = isRecord(body) && "detail" in body ? body.detail : body;
      ({ message, fieldErrors } = parseDetail(detail));
    } catch {
      message = text.length > 300 ? `${text.slice(0, 300)}…` : text;
    }
  }
  return new ApiError(message || fallback, response.status, detail, fieldErrors);
}

type Method = "GET" | "POST" | "PUT" | "DELETE";

export async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    // The server rejects changing requests without this header (CSRF guard).
    headers["X-Cratekeeper"] = "1";
  }
  const init: RequestInit = { method, headers, signal };
  if (body instanceof Blob) {
    // A file goes as it is (the server reads the raw body).
    headers["Content-Type"] = "application/octet-stream";
    init.body = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      "Cannot reach the Cratekeeper server. Is it still running?",
      0,
      null,
      [],
      { cause: error },
    );
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>("GET", path, undefined, signal),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
};
