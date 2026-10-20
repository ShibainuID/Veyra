import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentAction } from "../actions";
import { canPrepareAgain, groupActions, toLine } from "../approvals/queue";
import { EvidenceChecklist } from "./EvidenceChecklist";

describe("EvidenceChecklist", () => {
  const items = [
    { key: "identity_reference", label: "Passport muzzle reference", status: "present" as const, ref: "ref-78ad" },
    { key: "farmer_declaration", label: "Farmer declaration confirmed", status: "missing" as const, ref: null },
    { key: "vet_assessment", label: "Veterinary assessment", status: "missing" as const, ref: null },
  ];

  it("names each missing item in words and offers where to fix it", () => {
    render(
      <EvidenceChecklist
        items={items}
        renderFix={(item) => (item.key === "vet_assessment" ? <a href="#assessment">Ask the vet to add an assessment</a> : null)}
      />,
    );
    expect(screen.getByText((_, el) => el?.tagName === "P" && el.textContent === "2 of 3 requirements are missing.")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Present");
    expect(rows[0]).toHaveTextContent("ref-78ad");
    expect(rows[1]).toHaveTextContent("Missing");
    expect(rows[2]).toHaveTextContent("Missing");
    expect(within(rows[2]!).getByRole("link", { name: "Ask the vet to add an assessment" })).toHaveAttribute("href", "#assessment");
    expect(within(rows[0]!).queryByRole("link")).toBeNull();
  });

  it("says so when everything is on file", () => {
    render(<EvidenceChecklist items={items.map((i) => ({ ...i, status: "present" as const }))} />);
    expect(screen.getByText("Every requirement is on file.")).toBeInTheDocument();
    expect(screen.queryByText("Missing")).toBeNull();
  });
});

function action(overrides: Partial<AgentAction>): AgentAction {
  return {
    id: "act-1",
    action_type: "PREMIUM_PAYMENT",
    status: "pending_approval",
    version: 1,
    animal_id: "animal-demo-001",
    subject_type: "policy_application",
    subject_id: "app-1",
    supersedes_id: null,
    payload: {},
    payload_hash: "abcdef0123456789",
    rationale: null,
    proposed_by_type: "agent",
    proposed_by_id: "user-manager",
    expires_at: "2026-10-20T06:30:00Z",
    decided_by: null,
    decided_at: null,
    decision: null,
    decision_note: null,
    cancel_reason: null,
    created_at: "2026-10-20T06:00:00Z",
    updated_at: "2026-10-20T06:00:00Z",
    evidence_manifest: null,
    execution: null,
    review: { recipient: "Sandbox Mutual", animal_id: "animal-demo-001", amount_minor: 8_736, currency: "USD", terms_version: "sample-v1", evidence_manifest_version: 1, balance_after_minor: 969_902 },
    ...overrides,
  };
}

describe("approval queue", () => {
  it("groups by what the manager must do next", () => {
    const groups = groupActions([
      action({ id: "a", status: "pending_approval" }),
      action({ id: "b", status: "approved" }),
      action({ id: "c", status: "unknown" }),
      action({ id: "d", status: "failed" }),
      action({ id: "e", status: "declined" }),
    ]);
    expect(groups.map((g) => [g.id, g.items.map((i) => i.id)])).toEqual([
      ["awaiting", ["a"]],
      ["approved", ["b"]],
      ["unresolved", ["c"]],
      ["history", ["d", "e"]],
    ]);
  });

  it("prints a payment as a debit only when it can move the wallet", () => {
    expect(toLine(action({}), 2).amount).toEqual({ minor: -8_736, currency: "USD" });
    expect(toLine(action({}), 2).balanceMinor).toBe(969_902);
    expect(toLine(action({ status: "failed" }), 2).amount).toMatchObject({ minor: 8_736, label: "Not charged", signed: false });
  });

  it("offers a new version for closed lines but not superseded ones", () => {
    expect(canPrepareAgain(action({ status: "expired" }))).toBe(true);
    expect(canPrepareAgain(action({ status: "cancelled", cancel_reason: "approval_stale" }))).toBe(true);
    expect(canPrepareAgain(action({ status: "cancelled", cancel_reason: "superseded" }))).toBe(false);
    expect(canPrepareAgain(action({ status: "succeeded" }))).toBe(false);
  });
});
