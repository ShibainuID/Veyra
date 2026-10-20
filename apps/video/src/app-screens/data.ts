// The app's real seeded demo data (demo/fixtures/herd.json, policies.json, enrollment_samples.json), as the
// screens show it. Amounts are USD; value = weight range x 5.20 USD/kg (demo reference price, 2026-10-01).

export type Coverage = "covered" | "none";
export type Animal = {
  id: string;
  tag: string;
  name: string;
  kg: [number, number];
  coverage: Coverage;
  policy?: string;
  alert?: { tone: "uncertain" | "danger"; label: string };
  lastSeen?: string;
};

export const PRICE_PER_KG = 5.2;
export const usd = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const usd0 = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
export const valueRange = (a: Animal) => `${usd0(a.kg[0] * PRICE_PER_KG)}–${usd0(a.kg[1] * PRICE_PER_KG)}`;

export const SARI: Animal = {
  id: "animal-demo-001",
  tag: "001",
  name: "Sari",
  kg: [480, 560],
  coverage: "none",
  lastSeen: "CAM-01 · Pen A · feed line · 17:09",
};

export const BIMA: Animal = {
  id: "animal-demo-002",
  tag: "002",
  name: "Bima",
  kg: [520, 600],
  coverage: "covered",
  policy: "Basic Mortality & Accident",
  lastSeen: "Pen A · feed line",
};

export const HERD: Animal[] = [
  BIMA,
  { id: "animal-demo-003", tag: "003", name: "Melati", kg: [440, 512], coverage: "covered", policy: "Mortality + Theft" },
  { id: "animal-demo-004", tag: "004", name: "Gatot", kg: [580, 660], coverage: "none", alert: { tone: "uncertain", label: "Low visibility" } },
  { id: "animal-demo-005", tag: "005", name: "Dewi", kg: [560, 640], coverage: "none" },
  { id: "animal-demo-006", tag: "006", name: "Rama", kg: [470, 548], coverage: "none" },
];

export const FARM = "Wahyu Farms";
export const MANAGER = { name: "W. Santoso", initials: "W.S." };
export const OPERATOR = { name: "A. Pratama", initials: "A.P." };
export const VET = "dr. R. Lestari";
export const INSURER = "Sandbox Mutual";

// Sari's valuation and the three fictional sample-v1 products
export const SARI_VALUE: [number, number] = [SARI.kg[0] * PRICE_PER_KG, SARI.kg[1] * PRICE_PER_KG]; // 2,496 - 2,912
export const INSURED_VALUE = SARI_VALUE[0]; // cover written up to the lower bound (sample-v1 §1.2)

export type Plan = {
  id: string;
  name: string;
  status: "eligible" | "review" | "ineligible";
  statusLabel: string;
  reason: string;
  premium: string;
  covers: string;
  exclusion: string;
  gap: string;
};

export const PLANS: Plan[] = [
  {
    id: "basic-mortality",
    name: "Basic Mortality & Accident",
    status: "eligible",
    statusLabel: "Eligible",
    reason: "Identity, age and valuation confirmed",
    premium: `${usd(INSURED_VALUE * 0.035)} USD / yr`,
    covers: "Death · accidental injury",
    exclusion: "Pre-existing illness, neglect",
    gap: "No theft cover",
  },
  {
    id: "mortality-theft",
    name: "Mortality + Theft",
    status: "review",
    statusLabel: "Needs review",
    reason: "Add an ownership document reference",
    premium: `${usd(INSURED_VALUE * 0.052)} USD / yr`,
    covers: "Death · injury · theft",
    exclusion: "Theft without a police report in 72 h",
    gap: "Ownership document missing",
  },
  {
    id: "dairy-health-plus",
    name: "Dairy Health Plus",
    status: "ineligible",
    statusLabel: "Not eligible",
    reason: "Dairy breeds only",
    premium: "—",
    covers: "Illness · accidental injury",
    exclusion: "Illness within 14 days of start",
    gap: "Sari is a beef animal",
  },
];

export const PREMIUM = INSURED_VALUE * 0.035; // 87.36 USD
export const WALLET_BEFORE = 10000;
export const WALLET_AFTER = WALLET_BEFORE - PREMIUM; // 9,912.64

export const RECEIPTS = {
  application: "SBX-APP-0417",
  payment: "SBX-PAY-2291",
  policy: "SBX-POL-0417",
  claim: "SBX-CLM-0092",
};
