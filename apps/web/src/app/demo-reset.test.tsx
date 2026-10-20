import { calls, routeFetch } from "../test/fetch-mock";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { ToastProvider } from "../components/Toast";
import { resetRoleStoreForTests, setToken } from "../lib/role-store";
import { DemoReset } from "./DemoReset";

function renderReset() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <DemoReset compact />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  resetRoleStoreForTests();
  window.localStorage.clear();
  routeFetch(() => ({ body: { status: "reset", scenario: "post-enrollment", animals: 6 } }));
});

describe("DemoReset", () => {
  it("is a manager's control only", () => {
    setToken("demo-operator");
    renderReset();
    expect(screen.queryByRole("button", { name: "Demo" })).not.toBeInTheDocument();
  });

  it("asks inline before it resets, then resets to the chosen scenario", async () => {
    setToken("demo-manager");
    const user = userEvent.setup();
    renderReset();
    await user.click(screen.getByRole("button", { name: "Demo" }));
    await user.click(screen.getByRole("radio", { name: /After enrollment/ }));
    await user.click(screen.getByRole("button", { name: "Reset demo…" }));
    expect(calls).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Reset the demo" }));
    await waitFor(() => expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(["POST /api/v1/demo/reset?scenario=post-enrollment"]));
  });
});
