import { apiError, calls, routeFetch, type MockCall } from "../../test/fetch-mock";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ToastProvider } from "../../components/Toast";
import { resetRoleStoreForTests, setToken } from "../../lib/role-store";
import { ActionReview } from "./ActionReview";
import { useExecuteAction } from "./hooks";
import { IDEMPOTENCY_PREFIX, idempotencyKeyFor, resetIdempotencyKeysForTests } from "./idempotency";
import { outcomeToast } from "./outcome";
import type { AgentAction } from "./types";

function makeAction(overrides: Partial<AgentAction> = {}): AgentAction {
  return {
    id: "act-1",
    action_type: "PREMIUM_PAYMENT",
    status: "pending_approval",
    version: 1,
    animal_id: "animal-demo-002",
    subject_type: "animal",
    subject_id: "animal-demo-002",
    supersedes_id: null,
    payload: { amount_minor: 8736, currency: "USD" },
    payload_hash: "9ae76ede7226ddd8a29dec68ec8cc3ee",
    rationale: "Bima's premium is due.",
    proposed_by_type: "agent",
    proposed_by_id: "user-manager",
    expires_at: new Date(Date.now() + 20 * 60_000).toISOString(),
    decided_by: null,
    decided_at: null,
    decision: null,
    decision_note: null,
    cancel_reason: null,
    created_at: "2026-10-20T05:00:00Z",
    updated_at: "2026-10-20T05:00:00Z",
    evidence_manifest: {
      id: "man-1",
      version: 2,
      manifest_hash: "abc",
      items: [{ type: "valuation", ref: "val-1", label: "Valuation v1", sha256: null }],
    },
    execution: null,
    review: {
      recipient: "Sandbox Mutual",
      animal_id: "animal-demo-002",
      amount_minor: 8736,
      currency: "USD",
      terms_version: "sample-v1",
      evidence_manifest_version: 2,
      balance_after_minor: 491264,
    },
    ...overrides,
  };
}

const succeeded = (base: AgentAction): AgentAction => ({
  ...base,
  status: "succeeded",
  execution: {
    id: "exe-1",
    idempotency_key: "k",
    status: "succeeded",
    provider_id: "sandbox-payment",
    provider_receipt: { status: "succeeded", payment_ref: "SBX-PAY-42" },
    error: null,
    started_at: "2026-10-20T05:01:00Z",
    completed_at: "2026-10-20T05:01:01Z",
  },
});

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>
    );
  };
}

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

const executeCalls = () => calls.filter((c: MockCall) => c.path.endsWith("/execute"));

beforeEach(() => {
  resetIdempotencyKeysForTests();
  resetRoleStoreForTests();
  window.localStorage.clear();
});

afterEach(() => {
  resetIdempotencyKeysForTests();
});

describe("idempotency keys", () => {
  it("creates one key per action and persists it in sessionStorage", () => {
    const first = idempotencyKeyFor("act-1");
    expect(first).toMatch(/[0-9a-f-]{36}/);
    expect(idempotencyKeyFor("act-1")).toBe(first);
    expect(window.sessionStorage.getItem(`${IDEMPOTENCY_PREFIX}act-1`)).toBe(first);
    expect(idempotencyKeyFor("act-2")).not.toBe(first);
  });

  it("reuses the stored key after a reload (fresh memory, same session)", () => {
    window.sessionStorage.setItem(`${IDEMPOTENCY_PREFIX}act-9`, "stored-key");
    expect(idempotencyKeyFor("act-9")).toBe("stored-key");
  });
});

describe("useExecuteAction", () => {
  it("sends the same Idempotency-Key when a failed execution is retried", async () => {
    let attempt = 0;
    routeFetch(() => {
      attempt += 1;
      return attempt === 1 ? { status: 0 } : { body: succeeded(makeAction({ status: "approved" })) };
    });
    const client = newClient();
    const { result } = renderHook(() => useExecuteAction(), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync("act-1").catch(() => undefined);
    });
    await act(async () => {
      await result.current.mutateAsync("act-1");
    });

    const sent = executeCalls();
    expect(sent).toHaveLength(2);
    const key = sent[0]!.headers.get("Idempotency-Key");
    expect(key).toBeTruthy();
    expect(sent[1]!.headers.get("Idempotency-Key")).toBe(key);
  });

  it("uses a different key for a different action", async () => {
    routeFetch(() => ({ body: succeeded(makeAction({ status: "approved" })) }));
    const { result } = renderHook(() => useExecuteAction(), { wrapper: wrapper(newClient()) });
    await act(async () => {
      await result.current.mutateAsync("act-1");
      await result.current.mutateAsync("act-2");
    });
    const [a, b] = executeCalls();
    expect(a!.headers.get("Idempotency-Key")).not.toBe(b!.headers.get("Idempotency-Key"));
  });
});

describe("outcomeToast", () => {
  it("names the provider and the receipt", () => {
    expect(outcomeToast(succeeded(makeAction())).title).toBe("Sandbox Mutual received the payment · receipt SBX-PAY-42");
  });
});

describe("ActionReview", () => {
  it("shows what will execute, then approves with the reviewed hash and version and executes", async () => {
    const pending = makeAction();
    routeFetch(({ method, path }) => {
      if (method === "GET" && path === "/api/v1/agent/actions/act-1") return { body: pending };
      if (path.endsWith("/decision")) return { body: { ...pending, status: "approved" } };
      if (path.endsWith("/execute")) return { body: succeeded(pending) };
      return { body: { items: [] } };
    });
    render(<ActionReview actionId="act-1" lineNo={4} />, { wrapper: wrapper(newClient()) });

    expect(await screen.findByText("Sandbox Mutual")).toBeInTheDocument();
    expect(screen.getByText("sample-v1")).toBeInTheDocument();
    expect(screen.getByText("9ae76ede")).toBeInTheDocument();
    expect(screen.getByText(/Balance after line/)).toHaveTextContent("Balance after line 004");

    await userEvent.click(screen.getByRole("button", { name: /Approve and stamp/ }));

    await waitFor(() => expect(executeCalls()).toHaveLength(1));
    const decision = calls.find((c) => c.path.endsWith("/decision"))!;
    expect(decision.body).toMatchObject({ decision: "approve", payload_hash: pending.payload_hash, version: 1 });
    expect(executeCalls()[0]!.headers.get("Idempotency-Key")).toBeTruthy();
    expect(await screen.findByText("Sandbox Mutual received the payment · receipt SBX-PAY-42")).toBeInTheDocument();
  });

  it("replaces the buttons with an explanation and a new-version path when the approval is stale", async () => {
    const pending = makeAction();
    routeFetch(({ method, path }) => {
      if (method === "GET" && path === "/api/v1/agent/actions/act-1") return { body: pending };
      if (path.endsWith("/decision")) return apiError(409, "APPROVAL_STALE");
      return { body: { items: [] } };
    });
    render(<ActionReview actionId="act-1" />, { wrapper: wrapper(newClient()) });
    await userEvent.click(await screen.findByRole("button", { name: /Approve and stamp/ }));

    expect(await screen.findByText("The details changed after approval. Review the new version.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review the new version" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve and stamp/ })).not.toBeInTheDocument();
    expect(executeCalls()).toHaveLength(0);
  });

  it("shows an expired action without decision buttons", async () => {
    routeFetch(() => ({ body: makeAction({ status: "expired" }) }));
    render(<ActionReview actionId="act-1" />, { wrapper: wrapper(newClient()) });
    expect(await screen.findByText("This approval window has closed. Prepare the action again.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve and stamp/ })).not.toBeInTheDocument();
  });

  it("tells an operator that only a manager can approve", async () => {
    setToken("demo-operator");
    routeFetch(() => ({ body: makeAction() }));
    render(<ActionReview actionId="act-1" />, { wrapper: wrapper(newClient()) });
    expect(await screen.findByText("Only a manager can approve. Switch role to Manager.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve and stamp/ })).not.toBeInTheDocument();
  });

  it("declines with an optional note and never executes", async () => {
    const pending = makeAction();
    routeFetch(({ method, path }) => {
      if (method === "GET" && path === "/api/v1/agent/actions/act-1") return { body: pending };
      if (path.endsWith("/decision")) return { body: { ...pending, status: "declined" } };
      return { body: { items: [] } };
    });
    render(<ActionReview actionId="act-1" />, { wrapper: wrapper(newClient()) });
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));
    await userEvent.type(screen.getByLabelText(/Decline this premium payment/), "Wrong animal");
    await userEvent.click(screen.getByRole("button", { name: "Decline" }));

    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/decision"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/decision"))!.body).toMatchObject({ decision: "decline", note: "Wrong animal" });
    expect(executeCalls()).toHaveLength(0);
  });
});
