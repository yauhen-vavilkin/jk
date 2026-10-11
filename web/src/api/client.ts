// One fetch wrapper. The server's `message` is the sentence the interface
// shows, so an error carries it through unchanged.
import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Said when the request never reached JK: JK is down, not Jenkins. */
export const UNREACHABLE = "JK could not be reached.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // X-JK-Panel marks the request as the panel's own; the server refuses a
  // change without it, which no other website can add.
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        "X-JK-Panel": "1",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "unreachable", UNREACHABLE);
  }

  if (!response.ok) {
    let code = "request_failed";
    let message = `JK could not complete that request (HTTP ${response.status}).`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body?.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // A response without a JSON body keeps the sentence above.
    }
    throw new ApiError(response.status, code, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
};
