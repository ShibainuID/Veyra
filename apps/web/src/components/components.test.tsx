import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { EarTag } from "./EarTag";
import { ErrorNotice } from "./feedback";
import { FilterChips } from "./FilterChips";
import { PassbookLine } from "./PassbookLine";

describe("EarTag", () => {
  it("names the tag and its identity state", () => {
    render(<EarTag animalId="animal-demo-001" state="confirmed" />);
    expect(screen.getByRole("img", { name: "Ear tag 001, identity confirmed" })).toBeInTheDocument();
  });

  it("describes pending and unassigned tags", () => {
    render(
      <>
        <EarTag animalId="animal-demo-007" state="pending" size="md" />
        <EarTag state="none" size="xl" />
      </>,
    );
    expect(screen.getByRole("img", { name: "Ear tag 007, identity pending review" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "No ear tag, unassigned track" })).toBeInTheDocument();
  });
});

describe("PassbookLine", () => {
  it("shows an awaiting line with its stamp slot and countdown", () => {
    const expiresAt = new Date(Date.now() + 25 * 60_000).toISOString();
    render(
      <ol>
        <PassbookLine
          id="l4"
          number={4}
          at="2026-10-20T02:58:00Z"
          title="Premium payment 87.36 USD"
          detail="To Sandbox Mutual"
          amount={{ minor: -8_736 }}
          status="awaiting"
          expiresAt={expiresAt}
          timeZone="Asia/Jakarta"
        />
      </ol>,
    );
    const line = screen.getByRole("listitem");
    expect(line).toHaveAttribute("data-status", "awaiting");
    expect(within(line).getByText("004")).toBeInTheDocument();
    expect(line).toHaveTextContent(/Awaiting stamp · expires (24|25):\d\d/);
    expect(line).toHaveTextContent("−87.36 USD");
    expect(within(line).queryByText(/APPROVED/i)).not.toBeInTheDocument();
  });

  it("shows the stamp once posted", () => {
    render(
      <ol>
        <PassbookLine
          id="l3"
          number={3}
          at="2026-10-20T01:31:00Z"
          title="Application · Basic Mortality"
          status="posted"
          stamp={{ kind: "approved", at: "2026-10-20T01:31:00Z", by: "W.S." }}
          timeZone="Asia/Jakarta"
        />
      </ol>,
    );
    expect(screen.getByText("Approved · 20 OCT 08:31 · W.S.")).toBeInTheDocument();
    expect(screen.queryByText(/Awaiting stamp/)).not.toBeInTheDocument();
  });

  it("says when the approval window has closed", () => {
    render(
      <ol>
        <PassbookLine
          id="l5"
          number={5}
          at="2026-10-20T01:31:00Z"
          title="Premium payment"
          status="awaiting"
          expiresAt={new Date(Date.now() - 60_000).toISOString()}
        />
      </ol>,
    );
    expect(screen.getByRole("listitem")).toHaveTextContent("Expired · prepare again");
  });
});

describe("FilterChips", () => {
  it("toggles pressed state", async () => {
    function Harness() {
      const [value, setValue] = useState("all");
      return (
        <FilterChips
          label="Filter herd"
          value={value}
          onChange={setValue}
          options={[
            { value: "all", label: "All", count: 6 },
            { value: "uncovered", label: "Not covered", count: 3 },
          ]}
        />
      );
    }
    render(<Harness />);
    const uncovered = screen.getByRole("button", { name: /Not covered/ });
    expect(uncovered).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(uncovered);
    expect(uncovered).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /All/ })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("ErrorNotice", () => {
  it("prints plain copy for the code", () => {
    render(<ErrorNotice code="FORBIDDEN_ROLE" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Your role can't do this. Switch to Manager to approve.");
  });
});
