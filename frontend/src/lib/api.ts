/**
 * Typed client for /api/v1. Types come from the OpenAPI document the backend exports
 * (`npm run api:types`), so a renamed field fails the build instead of a user.
 *
 * Cookie auth: every write carries the CSRF token from the last /session response. A 403
 * "csrf" means the session was rotated (signed in elsewhere, server restart): refresh the
 * session once and retry. A 401 means sign in again.
 */
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "@/api/schema";

export type ApiPaths = paths;

let csrfToken = "";
let onUnauthorized: (() => void) | null = null;
let onTwoFactorSetup: (() => void) | null = null;

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export function getCsrfToken() {
  return csrfToken;
}

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

/** Called when a request is refused because the workspace requires two-factor and this person has none. */
export function setTwoFactorSetupHandler(fn: () => void) {
  onTwoFactorSetup = fn;
}

const auth: Middleware = {
  async onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      request.headers.set("X-CSRF-Token", csrfToken);
    }
    request.headers.set("Accept", "application/json");
    return request;
  },
  async onResponse({ request, response }) {
    if (response.status === 403) {
      const body = await response.clone().json().catch(() => null);
      if (body?.code === "csrf" && !request.headers.get("X-Spark-Retry")) {
        const s = await fetch("/api/v1/session", { credentials: "same-origin" }).then((r) => r.json());
        setCsrfToken(s.csrf_token);
        const retry = new Request(request, { headers: new Headers(request.headers) });
        retry.headers.set("X-CSRF-Token", csrfToken);
        retry.headers.set("X-Spark-Retry", "1");
        return fetch(retry);
      }
      if (body?.code === "two_factor_setup_required") onTwoFactorSetup?.();
    }
    if (response.status === 401) {
      const body = await response.clone().json().catch(() => null);
      if (body?.code === "login_required") onUnauthorized?.();
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: "/api/v1", credentials: "same-origin" });
api.use(auth);

export class ApiError extends Error {
  constructor(public status: number, public code: string, detail: string) {
    super(detail);
  }
}

/**
 * Unwrap an openapi-fetch result: data, or throw an ApiError with the server's code.
 * A successful answer with no body (204 after a delete) has no data and is not an error.
 */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    const e = (result.error ?? {}) as { code?: string; detail?: string };
    throw new ApiError(result.response.status, e.code ?? "error", e.detail ?? result.response.statusText);
  }
  return result.data as T;
}
