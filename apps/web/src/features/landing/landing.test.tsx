import { routeFetch } from "../../test/fetch-mock";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { NAV_ITEMS } from "../../app/nav";
import { routes } from "../../app/router";
import { ToastProvider } from "../../components/Toast";
import { STEP_IDS } from "./content";
import { stampCount } from "./stamps";

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  routeFetch(() => ({ status: 503, body: { error: { code: "UNAVAILABLE", message: "offline" } } }));
});

describe("stampCount", () => {
  const order = ["a", "b", "c", "d", "e"];

  it("stamps nothing before the first step is reached", () => {
    expect(stampCount(order, new Set())).toBe(0);
  });

  it("stamps the furthest step reached and every step before it", () => {
    expect(stampCount(order, new Set(["a", "b"]))).toBe(2);
    expect(stampCount(order, new Set(["c"]))).toBe(3);
    expect(stampCount(order, new Set(["a", "e"]))).toBe(5);
  });

  it("ignores ids that are not journey steps", () => {
    expect(stampCount(order, new Set(["proof"]))).toBe(0);
  });
});

describe("the pitch page at /", () => {
  it("renders the landing outside the app shell, with the demo one click away", () => {
    renderAt("/");
    expect(screen.getByRole("heading", { level: 1, name: "Know every animal. Protect every asset." })).toBeInTheDocument();
    const demoLinks = screen.getAllByRole("link", { name: /Open the live demo/ });
    expect(demoLinks.length).toBeGreaterThan(1);
    demoLinks.forEach((link) => expect(link).toHaveAttribute("href", "/herd"));
    expect(screen.getByRole("link", { name: "Watch the 5-minute journey" })).toHaveAttribute("href", "#journey");
    // No app tabs on the pitch page.
    expect(screen.queryByRole("link", { name: "Approvals" })).not.toBeInTheDocument();
  });

  it("tells the journey in five steps, each with a real screenshot", () => {
    renderAt("/");
    const journey = document.getElementById("journey")!;
    expect(within(journey).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "Step 1: Enrolled",
      "Step 2: Valued",
      "Step 3: Covered",
      "Step 4: Watched",
      "Step 5: Claimed",
    ]);
    const images = within(journey).getAllByRole("img").filter((img) => img.tagName === "IMG");
    // Five steps, plus the claim's guard (the refusal before the evidence was complete).
    expect(images).toHaveLength(6);
    const phoneCrops = journey.querySelectorAll('source[media="(max-width: 39.9375rem)"]');
    expect(phoneCrops).toHaveLength(5);
    phoneCrops.forEach((source) => expect(source.getAttribute("srcset")).toMatch(/^\/pitch\/.+-m\.webp$/));
    images.forEach((img) => {
      expect(img).toHaveAttribute("loading", "lazy");
      expect(img.getAttribute("src")).toMatch(/^\/pitch\/.+\.webp$/);
      expect(img.getAttribute("alt")?.length).toBeGreaterThan(40);
    });
    STEP_IDS.forEach((id) => expect(document.getElementById(id)).not.toBeNull());
  });

  it("shows every stamp when the stamps cannot be sequenced (no IntersectionObserver)", () => {
    renderAt("/");
    const tag = screen.getByRole("complementary", { name: "Sari · 001" });
    expect(within(tag).getByText("5 of 5 journey steps stamped.")).toBeInTheDocument();
  });
});

describe("the herd at /herd", () => {
  it("renders the herd inside the app shell, with Herd as the current tab", async () => {
    renderAt("/herd");
    expect(await screen.findByRole("heading", { level: 1, name: "Herd" })).toBeInTheDocument();
    const current = screen.getAllByRole("link", { name: "Herd" }).filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.length).toBeGreaterThan(0);
    current.forEach((link) => expect(link).toHaveAttribute("href", "/herd"));
    expect(screen.getByRole("link", { name: "VEYRA, go to the herd" })).toHaveAttribute("href", "/herd");
  });

  it("keeps animal pages under the Herd tab", () => {
    const herd = NAV_ITEMS.find((item) => item.label === "Herd")!;
    expect(herd.to).toBe("/herd");
    expect(herd.matches("/herd")).toBe(true);
    expect(herd.matches("/animals/animal-demo-001")).toBe(true);
    expect(herd.matches("/")).toBe(false);
  });
});
