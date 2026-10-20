import { describe, expect, it } from "vitest";
import type { AgentAction } from "../actions";
import { closedNote } from "./actions";

const action = (status: string, cancel_reason: string | null = null) => ({ status, cancel_reason }) as unknown as AgentAction;

describe("closedNote", () => {
  it("says why the last action closed without running", () => {
    expect(closedNote(action("declined"), "submission")).toMatch(/declined, so nothing was sent/);
    expect(closedNote(action("expired"), "submission")).toMatch(/expired before anyone decided/);
    expect(closedNote(action("cancelled", "approval_stale"), "submission")).toMatch(/records changed after/);
    expect(closedNote(action("failed"), "premium payment")).toBe("The last premium payment failed. Prepare it again.");
  });

  it("is silent while the action is open or once it succeeded", () => {
    expect(closedNote(undefined, "submission")).toBeNull();
    expect(closedNote(action("pending_approval"), "submission")).toBeNull();
    expect(closedNote(action("succeeded"), "submission")).toBeNull();
  });
});
