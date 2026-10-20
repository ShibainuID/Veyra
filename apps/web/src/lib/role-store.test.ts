import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { shouldRetry } from "./api";
import { ApiError } from "./errors";
import { DEFAULT_TOKEN, TOKEN_STORAGE_KEY, getToken, resetRoleStoreForTests, roleForToken, setToken } from "./role-store";

describe("role store", () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetRoleStoreForTests();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to the manager token", () => {
    expect(getToken()).toBe(DEFAULT_TOKEN);
    expect(roleForToken(getToken()).label).toBe("Manager");
  });

  it("persists a switch", () => {
    setToken("demo-operator");
    expect(getToken()).toBe("demo-operator");
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe("demo-operator");
    resetRoleStoreForTests();
    expect(getToken()).toBe("demo-operator");
  });

  it("ignores unknown stored tokens", () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "root");
    expect(getToken()).toBe(DEFAULT_TOKEN);
  });

  it("falls back to the manager when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(getToken()).toBe(DEFAULT_TOKEN);
    expect(() => setToken("demo-vet")).not.toThrow();
    expect(getToken()).toBe("demo-vet");
  });
});

describe("query retry", () => {
  it("never retries client errors", () => {
    expect(shouldRetry(0, new ApiError(404, "NOT_FOUND", "x"))).toBe(false);
    expect(shouldRetry(0, new ApiError(409, "APPROVAL_STALE", "x"))).toBe(false);
  });

  it("retries server and network errors twice", () => {
    expect(shouldRetry(0, new ApiError(500, "INTERNAL_ERROR", "x"))).toBe(true);
    expect(shouldRetry(1, ApiError.network())).toBe(true);
    expect(shouldRetry(2, ApiError.network())).toBe(false);
  });
});
