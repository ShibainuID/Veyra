/**
 * The demo role: which seeded bearer token the app sends. Stored in localStorage when it is
 * available; private windows and blocked storage fall back to the manager in memory.
 */
import { useSyncExternalStore } from "react";

export type Role = "manager" | "operator" | "vet";

export interface RoleOption {
  role: Role;
  label: string;
  token: string;
}

export const ROLE_OPTIONS: readonly RoleOption[] = [
  { role: "manager", label: "Manager", token: "demo-manager" },
  { role: "operator", label: "Operator", token: "demo-operator" },
  { role: "vet", label: "Vet", token: "demo-vet" },
];

export const DEFAULT_TOKEN = "demo-manager";
export const TOKEN_STORAGE_KEY = "veyra.demoToken";

const KNOWN_TOKENS = new Set(ROLE_OPTIONS.map((o) => o.token));

function readStoredToken(): string {
  try {
    const stored = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    return stored && KNOWN_TOKENS.has(stored) ? stored : DEFAULT_TOKEN;
  } catch {
    return DEFAULT_TOKEN;
  }
}

let currentToken: string | null = null;
const listeners = new Set<() => void>();

export function getToken(): string {
  if (currentToken === null) currentToken = readStoredToken();
  return currentToken;
}

export function setToken(token: string): void {
  const next = KNOWN_TOKENS.has(token) ? token : DEFAULT_TOKEN;
  currentToken = next;
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, next);
  } catch {
    // Storage unavailable: the choice lasts for this tab only.
  }
  for (const listener of listeners) listener();
}

export function roleForToken(token: string): RoleOption {
  return ROLE_OPTIONS.find((o) => o.token === token) ?? ROLE_OPTIONS[0]!;
}

/** Test hook: forget the cached token so the next read goes back to storage. */
export function resetRoleStoreForTests(): void {
  currentToken = null;
  listeners.clear();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useRole(): RoleOption {
  const token = useSyncExternalStore(subscribe, getToken, () => DEFAULT_TOKEN);
  return roleForToken(token);
}
