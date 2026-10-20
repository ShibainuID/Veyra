import { describe, expect, it } from "vitest";
import { agentHref } from "../../lib/agent-link";
import { documentKindLabel, formatBytes } from "./documents";

describe("passport documents", () => {
  it("prints file sizes the way the documents list shows them", () => {
    expect(formatBytes(900)).toBe("900 B");
    expect(formatBytes(2435)).toBe("2.4 KB");
    expect(formatBytes(2_300_672)).toBe("2.2 MB");
  });

  it("names every document kind", () => {
    expect(documentKindLabel("ownership")).toBe("Ownership");
    expect(documentKindLabel("purchase_receipt")).toBe("Purchase receipt");
    expect(documentKindLabel("vet_record")).toBe("Vet record");
  });
});

describe("agent links", () => {
  it("keep the fixed /agent?animal=&intent= contract", () => {
    expect(agentHref("animal-demo-001", "find_insurance")).toBe("/agent?animal=animal-demo-001&intent=find_insurance");
    expect(agentHref("animal-demo-003", "file_claim")).toBe("/agent?animal=animal-demo-003&intent=file_claim");
  });
});
