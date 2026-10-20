/**
 * One Idempotency-Key per approved action. The key is kept in sessionStorage under the action ID,
 * so a retry after a dropped connection or a reload sends the same key and the provider runs the
 * action at most once. When storage is unavailable the key lives in memory for this tab.
 */

export const IDEMPOTENCY_PREFIX = "veyra.idempotency.";

const memory = new Map<string, string>();

function newKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function read(actionId: string): string | null {
  try {
    const stored = window.sessionStorage.getItem(IDEMPOTENCY_PREFIX + actionId);
    if (stored) return stored;
  } catch {
    // Storage blocked: fall back to memory.
  }
  return memory.get(actionId) ?? null;
}

/** The key for this action, created (and remembered) on first use. */
export function idempotencyKeyFor(actionId: string): string {
  const existing = read(actionId);
  if (existing) return existing;
  const key = newKey();
  memory.set(actionId, key);
  try {
    window.sessionStorage.setItem(IDEMPOTENCY_PREFIX + actionId, key);
  } catch {
    // Memory copy is enough for this tab.
  }
  return key;
}

/** Test hook. */
export function resetIdempotencyKeysForTests(): void {
  memory.clear();
  try {
    for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
      const name = window.sessionStorage.key(i);
      if (name?.startsWith(IDEMPOTENCY_PREFIX)) window.sessionStorage.removeItem(name);
    }
  } catch {
    // Nothing stored.
  }
}
