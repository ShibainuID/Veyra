/**
 * A fetch mock for API tests. Import it FIRST in a test file: the typed client captures
 * `fetch` and `Request` when `lib/api` loads, and builds relative URLs that Node's Request
 * rejects, so this module installs a relative-URL Request and a routable fetch before that.
 */
import { vi } from "vitest";

export interface MockCall {
  method: string;
  path: string;
  headers: Headers;
  body: unknown;
}

type Handler = (call: MockCall) => { status?: number; body?: unknown } | Promise<{ status?: number; body?: unknown }>;

const NativeRequest = globalThis.Request;
class RelativeRequest extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" && input.startsWith("/") ? `http://localhost${input}` : input, init);
  }
}
globalThis.Request = RelativeRequest as typeof Request;

let handler: Handler = () => ({ status: 500, body: { error: { code: "HTTP_ERROR", message: "No handler" } } });
export const calls: MockCall[] = [];

export const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const request = input instanceof NativeRequest ? input : new RelativeRequest(input as string, init);
  const url = new URL(request.url);
  const text = request.method === "GET" ? "" : await request.clone().text();
  const call: MockCall = {
    method: request.method,
    path: url.pathname + url.search,
    headers: request.headers,
    body: text ? JSON.parse(text) : undefined,
  };
  calls.push(call);
  const result = await handler(call);
  if (result.status === 0) throw new TypeError("Failed to fetch");
  return new Response(result.body === undefined ? null : JSON.stringify(result.body), {
    status: result.status ?? 200,
    headers: { "Content-Type": "application/json" },
  });
});
globalThis.fetch = fetchMock as typeof fetch;

export function routeFetch(next: Handler): void {
  handler = next;
  calls.length = 0;
  fetchMock.mockClear();
}

export function apiError(status: number, code: string, message = code) {
  return { status, body: { error: { code, message, details: {} } } };
}
