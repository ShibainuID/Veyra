import { calls, routeFetch } from "../../test/fetch-mock";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { resetRoleStoreForTests } from "../../lib/role-store";
import type { Claim, Passport } from "../finance/api";
import { CameraGallery } from "../passport/CameraGallery";
import type { CameraOut } from "../passport/api";
import type { IdentityCheck } from "./api";
import { IdentityCheckStep } from "./IdentityCheck";

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeCheck(overrides: Partial<IdentityCheck> = {}): IdentityCheck {
  return {
    id: "idc-1",
    claim_id: "clm-1",
    animal_id: "animal-demo-001",
    outcome: "mismatch",
    reason: "Muzzle scan matched Bima (animal-demo-002), not Sari",
    matched_animal_id: "animal-demo-002",
    matched_animal_name: "Bima",
    candidates: [],
    inliers: 27,
    accept_inliers: 5,
    source: "simulated",
    method_version: "identity_check_fixture_v1",
    input: "sample",
    fallback: null,
    checked_by: "user-operator",
    checked_by_name: "A. Pratama",
    created_at: "2026-10-20T05:00:00Z",
    scan: { media_url: null, content_type: null, crop_url: null },
    reference: { reference_id: "ref-1", crop_url: null, frame_url: null, note: "sample enrollment, footage not attached" },
    ...overrides,
  };
}

function makeClaim(checks: IdentityCheck[]): Claim {
  return {
    id: "clm-1",
    animal_id: "animal-demo-001",
    identity_checks: checks,
    identity_check_required: true,
    incident_kind: "death",
  } as unknown as Claim;
}

describe("IdentityCheckStep", () => {
  beforeEach(() => routeFetch(() => ({ status: 201, body: { check: makeCheck({ outcome: "match" }), claim: makeClaim([]) } })));

  it("shows a mismatch, names the other animal, and says it blocks submission", () => {
    wrap(<IdentityCheckStep claim={makeClaim([makeCheck()])} animalName="Sari" role="operator" locked={false} />);
    expect(screen.getByText("Mismatch")).toBeInTheDocument();
    expect(screen.getByText("Muzzle scan matched Bima (animal-demo-002), not Sari")).toBeInTheDocument();
    expect(screen.getByText(/A mismatch blocks submission/)).toBeInTheDocument();
    expect(screen.getByText("Enrolled muzzle")).toBeInTheDocument();
    expect(screen.getByText("Claim scan")).toBeInTheDocument();
    expect(screen.getAllByText("simulated").length).toBeGreaterThan(0);
  });

  it("runs a demo sample as JSON", async () => {
    wrap(<IdentityCheckStep claim={makeClaim([])} animalName="Sari" role="manager" locked={false} />);
    expect(screen.getByText(/No scan yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use sample: matching scan" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/v1/claims/clm-1/identity-checks")).toBe(true));
    const call = calls.find((c) => c.path === "/api/v1/claims/clm-1/identity-checks")!;
    expect(call.body).toEqual({ sample: "match" });
    expect(call.method).toBe("POST");
  });

  it("offers no scan to a vet, or once the claim is submitted", () => {
    const { unmount } = wrap(<IdentityCheckStep claim={makeClaim([])} animalName="Sari" role="vet" locked={false} />);
    expect(screen.queryByRole("button", { name: /Use sample/ })).toBeNull();
    expect(screen.getByText("A manager or operator scans the muzzle.")).toBeInTheDocument();
    unmount();
    wrap(<IdentityCheckStep claim={makeClaim([makeCheck({ outcome: "match", reason: null })])} animalName="Sari" role="manager" locked />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/Identity verified/)).toBeInTheDocument();
  });
});

function camera(id: string, synced: number | null, current = 12): CameraOut {
  return {
    id,
    name: id,
    location: "Pen",
    map_x: 0,
    map_y: 0,
    last_observation: null,
    gallery: {
      current_version: current,
      synced_version: synced,
      synced_at: synced ? new Date(Date.now() - 2 * 60_000).toISOString() : null,
      in_sync: synced === current,
      source: synced ? "simulated" : null,
    },
  };
}

const passport = {
  animal: { id: "animal-demo-001", name: "Sari", identity_status: "confirmed" },
  references: [{ id: "ref-1", view: "muzzle", crop_url: "/m.jpg", media_url: null }],
} as unknown as Passport;

describe("CameraGallery", () => {
  beforeEach(() => {
    resetRoleStoreForTests();
    routeFetch((call) =>
      call.path === "/api/v1/cameras"
        ? { body: { items: [camera("cam-pen-a", 12), camera("cam-pen-b", 12), camera("cam-pen-c", null)] } }
        : { body: { version: 12, published_at: "2026-10-20T05:00:00Z", acknowledged: ["cam-pen-a"], source: "simulated", cameras: {} } },
    );
  });

  it("says which pen cameras know the animal and which are not synced", async () => {
    wrap(<CameraGallery passport={passport} />);
    const summary = await screen.findByText(/Pen cameras know Sari:/);
    expect(summary.closest("p")).toHaveTextContent("Pen cameras know Sari: gallery v12 synced 2 min ago on cam-pen-a, cam-pen-b; cam-pen-c not synced yet.");
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[2]!).getByText("Not synced")).toBeInTheDocument();
  });

  it("lets the manager push the gallery to the cameras", async () => {
    wrap(<CameraGallery passport={passport} />);
    await userEvent.click(await screen.findByRole("button", { name: "Push to cameras" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/cameras/gallery/publish")).toBe(true));
    expect(await screen.findByText(/acknowledged/)).toBeInTheDocument();
  });
});
