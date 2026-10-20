/**
 * The typed API client (openapi-fetch over the generated `api-types.ts`), the shared query
 * client, and a small `request` helper for endpoints the exported schema doesn't describe yet.
 * Every call carries the demo bearer token from the role store, and every non-2xx response
 * becomes an `ApiError` built from the error envelope.
 */
import { QueryClient } from "@tanstack/react-query";
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./api-types";
import { ApiError } from "./errors";
import { getToken } from "./role-store";

export const API_BASE = "/api/v1";

const authMiddleware: Middleware = {
  onRequest({ request }) {
    request.headers.set("Authorization", `Bearer ${getToken()}`);
    return request;
  },
};

const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (!response.ok) throw await ApiError.fromResponse(response.clone());
    return response;
  },
  onError({ error }) {
    return error instanceof ApiError ? error : ApiError.network(error);
  },
};

/**
 * The exported schema's paths already carry the `/api/v1` prefix (routers mount under it), so the
 * typed client resolves against the origin: `api.GET("/api/v1/health")`.
 */
export const api = createClient<paths>({ baseUrl: "" });
api.use(authMiddleware, errorMiddleware);

/** Untyped JSON request for endpoints not yet in the exported OpenAPI document. */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${getToken()}`);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (cause) {
    throw ApiError.network(cause);
  }
  if (!response.ok) throw await ApiError.fromResponse(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.isClientError) return false;
  return failureCount < 2;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        staleTime: 15_000,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export const queryClient = createQueryClient();
