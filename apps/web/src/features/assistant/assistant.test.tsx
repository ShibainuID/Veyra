import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { factLink, missingCopy, type AssistantAnswer } from "./answer";
import { AnswerCard } from "./AnswerCard";

const records = { animals: [], last_observations: [], coverage: [], alerts: [] };

function renderAnswer(answer: AssistantAnswer) {
  return render(
    <MemoryRouter>
      <AnswerCard answer={answer} />
    </MemoryRouter>,
  );
}

describe("AnswerCard", () => {
  it("states missing evidence plainly, with the animal's name", () => {
    renderAnswer({
      intent: "location_lookup",
      parsed_by: "simulated",
      answer: "No camera observation is on record for Dewi (animal-demo-005).",
      facts: [],
      records: { ...records, animals: [{ id: "animal-demo-005", name: "Dewi" }] },
      missing: ["last_observation"],
      fallback_reason: "llm_offline",
    });
    const missing = screen.getByRole("list", { name: "Missing evidence" });
    expect(within(missing).getByText("No camera observation is on record for Dewi.")).toBeInTheDocument();
    expect(screen.getByText(/Parsed offline/)).toBeInTheDocument();
  });

  it("links facts to their records and credits a live parse", () => {
    renderAnswer({
      intent: "location_lookup",
      parsed_by: "live",
      answer: "Sari (animal-demo-001) was last observed on Pen A.",
      facts: [
        { label: "Last observed on", value: "Pen A · feed line", record_type: "camera", record_id: "cam-pen-a" },
        { label: "Coverage", value: "none", record_type: "animal", record_id: "animal-demo-001" },
      ],
      records: { ...records, animals: [{ id: "animal-demo-001", name: "Sari" }] },
      missing: ["active_policy"],
      fallback_reason: null,
    });
    expect(screen.getByText("No active policy is on record for Sari.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open in Monitor/ })).toHaveAttribute(
      "href",
      "/monitor?camera=cam-pen-a&animal=animal-demo-001",
    );
    expect(screen.getByRole("link", { name: /Open passport/ })).toHaveAttribute("href", "/animals/animal-demo-001");
    expect(screen.getByText(/Claude parsed this question/)).toBeInTheDocument();
    expect(screen.queryByText(/Parsed offline/)).not.toBeInTheDocument();
  });
});

describe("answer helpers", () => {
  it("never drops an unknown missing code", () => {
    expect(missingCopy("teeth_photo", "Bima")).toBe("Not on record: teeth photo for Bima.");
    expect(missingCopy("last_observation", null)).toBe("No camera observation is on record for this animal.");
  });

  it("sends alerts to the drawer", () => {
    expect(factLink({ label: "x", value: "y", record_type: "alert", record_id: "alr-1" }, null)).toEqual({
      to: "/alerts/alr-1",
      label: "Open alert",
    });
  });
});
