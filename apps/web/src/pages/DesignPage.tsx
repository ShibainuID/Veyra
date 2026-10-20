/*
 * /_design: every piece of the Ear Tag vocabulary in every state, with real VEYRA content.
 * Development only (the route is not registered in production builds). Used for visual QA.
 */
import { ClipboardList, Plus, RotateCcw, ScanLine, Send, Stamp as StampIcon, Trash2, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import {
  Button,
  DataTable,
  Drawer,
  EarTag,
  EmptyState,
  ErrorNotice,
  EvidenceFrame,
  FilterChips,
  IconButton,
  LoadingRegion,
  Money,
  Mono,
  PageHeader,
  PassbookLine,
  PassbookPanel,
  Provenance,
  Range,
  Section,
  Skeleton,
  Stamp,
  StatusPill,
  Timestamp,
  useToast,
  type Column,
  type EarTagState,
  type PassbookLineData,
  type StampKind,
  type StatusTone,
} from "../components";
import { ERROR_COPY, type ErrorCode } from "../lib/errors";
import { formatStampTime } from "../lib/format";
import { useRole } from "../lib/role-store";
import { Page } from "./Page";
import { QualityMeter } from "../features/enrollment/QualityMeter";
import { scoreGray, type ScanQuality } from "../features/enrollment/scan-quality";

const TZ = "Asia/Jakarta";
const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
const minutesFromNow = (m: number) => new Date(Date.now() + m * 60_000).toISOString();

/* ---------- Demo data ---------- */

interface HerdRow {
  id: string;
  tag: EarTagState;
  name: string;
  description: string;
  exposure: [number, number] | null;
  coverage: { tone: StatusTone; label: string } | null;
  lastSeen: { at: string; camera: string } | null;
  alert: { tone: StatusTone; label: string } | null;
}

const HERD: HerdRow[] = [
  {
    id: "animal-demo-001",
    tag: "confirmed",
    name: "Sari",
    description: "Bali cattle · F",
    exposure: [249_600, 291_200],
    coverage: { tone: "awaiting", label: "Premium awaiting stamp" },
    lastSeen: { at: minutesAgo(2), camera: "cam-pen-a" },
    alert: { tone: "danger", label: "Reduced movement" },
  },
  {
    id: "animal-demo-002",
    tag: "confirmed",
    name: "Bima",
    description: "Ongole · M",
    exposure: [270_400, 312_000],
    coverage: { tone: "ok", label: "Active · Basic Mortality" },
    lastSeen: { at: minutesAgo(4), camera: "cam-pen-a" },
    alert: null,
  },
  {
    id: "animal-demo-003",
    tag: "confirmed",
    name: "Melati",
    description: "Brahman cross · F",
    exposure: [228_800, 266_200],
    coverage: { tone: "ok", label: "Active · Mortality + Theft" },
    lastSeen: { at: minutesAgo(13), camera: "cam-pen-b" },
    alert: null,
  },
  {
    id: "animal-demo-004",
    tag: "confirmed",
    name: "Gatot",
    description: "Limousin cross · M",
    exposure: [301_600, 343_200],
    coverage: { tone: "neutral", label: "Not covered" },
    lastSeen: { at: minutesAgo(16 * 60 + 37), camera: "cam-pen-b" },
    alert: { tone: "uncertain", label: "Low visibility" },
  },
  {
    id: "animal-demo-007",
    tag: "pending",
    name: "New candidate",
    description: "Enrollment awaiting review",
    exposure: null,
    coverage: { tone: "neutral", label: "Not covered" },
    lastSeen: null,
    alert: null,
  },
  {
    id: "track-t-14",
    tag: "none",
    name: "Track t-14",
    description: "Unassigned · cam-pen-b",
    exposure: null,
    coverage: null,
    lastSeen: { at: minutesAgo(0.5), camera: "cam-pen-b" },
    alert: null,
  },
];

const dash = <span className="text-muted">—</span>;

const HERD_COLUMNS: Column<HerdRow>[] = [
  { id: "tag", header: "Tag", width: "96px", lead: true, cell: (r) => <EarTag animalId={r.id} state={r.tag} size="sm" /> },
  {
    id: "animal",
    header: "Animal",
    primary: true,
    sortValue: (r) => r.name,
    cell: (r) => (
      <span className="flex flex-col">
        <span>{r.name}</span>
        <span className="text-sm font-regular text-muted">{r.description}</span>
      </span>
    ),
  },
  {
    id: "exposure",
    header: "Exposure",
    sortValue: (r) => r.exposure?.[0],
    cell: (r) => (r.exposure ? <Money low={r.exposure[0]} high={r.exposure[1]} /> : dash),
  },
  {
    id: "coverage",
    header: "Coverage",
    cell: (r) => (r.coverage ? <StatusPill tone={r.coverage.tone} label={r.coverage.label} /> : dash),
  },
  {
    id: "seen",
    header: "Last observed",
    sortValue: (r) => (r.lastSeen ? -new Date(r.lastSeen.at).getTime() : null),
    cell: (r) =>
      r.lastSeen ? (
        <span className="flex flex-col">
          <Timestamp value={r.lastSeen.at} mode="relative" />
          <Mono className="text-sm text-muted">{r.lastSeen.camera}</Mono>
        </span>
      ) : (
        <span className="text-muted">No camera observation</span>
      ),
  },
  {
    id: "alerts",
    header: "Alerts",
    cell: (r) => (r.alert ? <StatusPill tone={r.alert.tone} label={r.alert.label} /> : dash),
  },
];

const BASE_LINES: PassbookLineData[] = [
  {
    id: "l1",
    number: 1,
    at: "2026-10-20T01:12:00Z",
    title: "Enrolled from guided video",
    detail: "Muzzle, teeth, and body references",
    status: "posted",
    source: "prototype",
    stamp: { kind: "confirmed", at: "2026-10-20T01:14:00Z", by: "OPR" },
  },
  {
    id: "l2",
    number: 2,
    at: "2026-10-20T01:20:00Z",
    title: "Valued 2,496.00–2,912.00 USD",
    detail: "480–560 kg × 5.20 USD/kg · price list 01 Oct 2026",
    status: "posted",
    source: "simulated",
  },
  {
    id: "l3",
    number: 3,
    at: "2026-10-20T01:31:00Z",
    title: "Application · Basic Mortality",
    detail: "Sandbox Mutual · terms sample-v1",
    amount: { minor: 249_600, label: "Insured" },
    status: "posted",
    stamp: { kind: "approved", at: "2026-10-20T01:31:00Z", by: "W.S." },
  },
];

function premiumLine(expiresAt: string): PassbookLineData {
  return {
    id: "l4",
    number: 4,
    at: minutesAgo(5),
    title: "Premium payment 87.36 USD",
    detail: "To Sandbox Mutual · app-7f3a · hash 9c41e2",
    amount: { minor: -8_736 },
    status: "awaiting",
    expiresAt,
  };
}

/* ---------- Capture quality specimens ---------- */

/** A synthetic 160x136 guide-box sample: ridged texture at `level` grey, softened by `blurPasses` box blurs. */
function syntheticQuality(level: number, contrast: number, blurPasses: number): ScanQuality {
  const w = 160;
  const h = 136;
  let gray = new Float32Array(w * h);
  let seed = 11;
  for (let i = 0; i < gray.length; i++) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const x = i % w;
    const y = Math.floor(i / w);
    gray[i] = Math.min(255, Math.max(0, level + contrast * (0.6 * Math.sin(x * 0.9) * Math.cos(y * 0.7) + 0.8 * (seed / 2 ** 32 - 0.5))));
  }
  for (let pass = 0; pass < blurPasses; pass++) {
    const next = new Float32Array(gray.length);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let sum = 0;
        let n = 0;
        for (let dy = -2; dy <= 2; dy++) {
          for (let dx = -2; dx <= 2; dx++) {
            if (y + dy < 0 || y + dy >= h || x + dx < 0 || x + dx >= w) continue;
            sum += gray[(y + dy) * w + x + dx]!;
            n++;
          }
        }
        next[y * w + x] = sum / n;
      }
    }
    gray = next;
  }
  return scoreGray(gray, w, h);
}

function QualitySpecimens() {
  const samples = useMemo(
    () => [
      { label: "Sharp, close muzzle", quality: syntheticQuality(128, 120, 0) },
      { label: "Blurred or too far", quality: syntheticQuality(128, 120, 2) },
      { label: "Too dark", quality: syntheticQuality(26, 30, 0) },
    ],
    [],
  );
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {samples.map((sample) => (
        <Specimen key={sample.label} label={`${sample.label} (synthetic frame)`}>
          <div className="rounded-panel bg-shell p-4">
            <QualityMeter quality={sample.quality} />
          </div>
        </Specimen>
      ))}
    </div>
  );
}

/* ---------- Gallery helpers ---------- */

function Specimen({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <p className="mb-2 text-sm font-bold text-muted">{label}</p>
      {children}
    </div>
  );
}

function Row({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-4">{children}</div>;
}

/* ---------- Interactive passbook ---------- */

type Outcome = "awaiting" | "approved" | "declined";

function PassbookDemo() {
  const role = useRole();
  const toast = useToast();
  const [outcome, setOutcome] = useState<Outcome>("awaiting");
  const [busy, setBusy] = useState<"approve" | "decline" | null>(null);
  const [expiresAt, setExpiresAt] = useState(() => minutesFromNow(24.85));
  const [stampedAt, setStampedAt] = useState<string | null>(null);

  const lines = useMemo<PassbookLineData[]>(() => {
    const line = premiumLine(expiresAt);
    if (outcome === "approved" && stampedAt) {
      return [
        ...BASE_LINES,
        { ...line, status: "posted", balanceMinor: 991_264, stamp: { kind: "posted", at: stampedAt, by: "W.S.", press: true } },
      ];
    }
    if (outcome === "declined" && stampedAt) {
      return [...BASE_LINES, { ...line, status: "void", stamp: { kind: "declined", at: stampedAt, by: "W.S.", press: true } }];
    }
    return [...BASE_LINES, line];
  }, [outcome, expiresAt, stampedAt]);

  const act = (kind: "approve" | "decline") => {
    setBusy(kind);
    window.setTimeout(() => {
      setBusy(null);
      setStampedAt(new Date().toISOString());
      setOutcome(kind === "approve" ? "approved" : "declined");
      toast.show(
        kind === "approve"
          ? { title: "Line 004 stamped and posted", body: "87.36 USD paid to Sandbox Mutual.", tone: "ok" }
          : { title: "Line 004 declined", body: "Nothing was paid. The agent can prepare it again.", tone: "neutral" },
      );
    }, 900);
  };

  const reset = () => {
    setOutcome("awaiting");
    setStampedAt(null);
    setExpiresAt(minutesFromNow(24.85));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-[440px] overflow-hidden rounded-panel border-2 border-ink">
        <PassbookPanel
          animal={{ id: "animal-demo-001", name: "Sari", tagState: "confirmed", description: "Bali cattle · F · 24–30 mo" }}
          facts={[
            { label: "Weight", value: <Range low={480} high={560} unit="kg" />, source: "prototype" },
            { label: "Age", value: <Range low={24} high={30} unit="mo" />, source: "simulated" },
            { label: "Indicative value", value: <Money low={249_600} high={291_200} /> },
            { label: "Last observed", value: "09:42 pen A", source: "live" },
          ]}
          summary={{ exposureLowMinor: 249_600, exposureHighMinor: 291_200, insuredMinor: 249_600 }}
          lines={lines}
          timeZone={TZ}
          decision={{
            balanceAfterMinor: 991_264,
            onApprove: () => act("approve"),
            onDecline: () => act("decline"),
            approving: busy === "approve",
            declining: busy === "decline",
            canApprove: role.role === "manager",
          }}
        />
      </div>
      {outcome !== "awaiting" && (
        <div>
          <Button icon={RotateCcw} onClick={reset}>
            Reset the demo line
          </Button>
        </div>
      )}
    </div>
  );
}

/* ---------- Page ---------- */

const STAMP_KINDS: StampKind[] = ["approved", "posted", "confirmed", "declined", "failed", "unknown"];
const TONES: Array<{ tone: StatusTone; label: string }> = [
  { tone: "ok", label: "Active" },
  { tone: "danger", label: "Payment failed" },
  { tone: "uncertain", label: "Identity uncertain" },
  { tone: "neutral", label: "Not covered" },
  { tone: "awaiting", label: "Awaiting stamp" },
];

export default function DesignPage() {
  const toast = useToast();
  const [filter, setFilter] = useState("all");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pressKey, setPressKey] = useState(0);
  const [loadingDemo, setLoadingDemo] = useState(false);

  const filteredHerd = useMemo(() => {
    if (filter === "uncovered") return HERD.filter((r) => r.coverage?.label === "Not covered");
    if (filter === "alerts") return HERD.filter((r) => r.alert);
    if (filter === "unassigned") return HERD.filter((r) => r.tag === "none");
    return HERD;
  }, [filter]);

  return (
    <Page>
      <PageHeader
        title="Component gallery"
        meta="Every piece of the Ear Tag vocabulary in every state, with real VEYRA content. Development only."
      />

      <Section title="Ear tags" description="Solid tag: identity confirmed. Dashed outline: pending review. Grey: an unassigned track.">
        <div className="flex flex-col gap-6">
          {(["confirmed", "pending", "none"] as const).map((state) => (
            <Specimen key={state} label={state}>
              <Row>
                <EarTag animalId={state === "pending" ? "animal-demo-007" : "animal-demo-001"} state={state} size="sm" />
                <EarTag animalId={state === "pending" ? "animal-demo-007" : "animal-demo-001"} state={state} size="md" />
                <EarTag animalId={state === "pending" ? "animal-demo-007" : "animal-demo-001"} state={state} size="xl" />
              </Row>
            </Specimen>
          ))}
          <Specimen label="On the black shell">
            <div className="inline-flex gap-4 rounded-panel bg-shell p-4">
              <EarTag animalId="animal-demo-002" state="confirmed" size="md" />
              <EarTag animalId="animal-demo-002" state="confirmed" size="sm" />
            </div>
          </Specimen>
        </div>
      </Section>

      <Section
        title="Stamps"
        description="The signature move. A stamp lands on its exact line with one short press; with reduced motion it simply appears."
        actions={
          <Button icon={StampIcon} onClick={() => setPressKey((k) => k + 1)}>
            Replay the press
          </Button>
        }
      >
        <Row>
          {STAMP_KINDS.map((kind) => (
            <Stamp key={`${kind}-${pressKey}`} kind={kind} at="2026-10-20T01:31:00Z" by="W.S." timeZone={TZ} press={pressKey > 0} />
          ))}
        </Row>
        <p className="mt-3 text-sm text-muted">
          Composed text, for example: <Mono>{`APPROVED · ${formatStampTime("2026-10-20T01:31:00Z", TZ)} · W.S.`}</Mono>
        </p>
      </Section>

      <Section title="Passbook" description="The selected tag's passbook. Approve or decline line 004 to see it post; switch role to Operator to see approval locked.">
        <PassbookDemo />
      </Section>

      <Section title="Passbook lines" description="Posted, awaiting with a live countdown, awaiting past its window, and void.">
        <ol className="pb-list max-w-[560px] rounded-panel border-2 border-line px-1">
          <PassbookLine {...BASE_LINES[2]!} timeZone={TZ} />
          <PassbookLine {...premiumLine(minutesFromNow(24.85))} timeZone={TZ} />
          <PassbookLine {...premiumLine(minutesAgo(1))} id="l4x" number={5} timeZone={TZ} />
          <PassbookLine
            id="l6"
            number={6}
            at="2026-10-19T09:05:00Z"
            title="Premium payment 91.20 USD"
            detail="Superseded by line 004 after the terms changed"
            amount={{ minor: -9_120 }}
            status="void"
            stamp={{ kind: "declined", at: "2026-10-19T09:10:00Z", by: "W.S." }}
            timeZone={TZ}
          />
          <PassbookLine
            id="l7"
            number={7}
            at="2026-10-19T08:00:00Z"
            title="Sandbox wallet funded"
            detail="Demo reset"
            amount={{ minor: 1_000_000 }}
            balanceMinor={1_000_000}
            status="posted"
            stamp={{ kind: "posted", at: "2026-10-19T08:00:00Z", by: "SYS" }}
            source="simulated"
            timeZone={TZ}
          />
        </ol>
      </Section>

      <Section title="Herd table" description="Tag column first, 64px rows, sortable headers, and the whole row links to the passport. Below 720px of width, rows stack.">
        <div className="flex flex-col gap-4">
          <FilterChips
            label="Filter herd"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All", count: HERD.length },
              { value: "uncovered", label: "Not covered", count: 2 },
              { value: "alerts", label: "Alerts", count: 2 },
              { value: "unassigned", label: "Unassigned tracks", count: 1 },
              { value: "review", label: "Identity review", count: 0, disabled: true },
            ]}
          />
          <DataTable
            caption="Herd: tag, animal, exposure, coverage, last observation, and alerts"
            columns={HERD_COLUMNS}
            rows={filteredHerd}
            rowKey={(r) => r.id}
            rowHref={(r) => (r.tag === "none" ? `/monitor` : `/animals/${r.id}`)}
            selectedKey="animal-demo-001"
            defaultSort={null}
            empty={
              <EmptyState title="No animals match this filter" headingLevel={3}>
                Choose All to see the whole herd.
              </EmptyState>
            }
          />
          <Specimen label="Loading">
            <DataTable caption="Herd (loading)" columns={HERD_COLUMNS} rows={[]} rowKey={(r) => r.id} loading loadingRows={2} />
          </Specimen>
          <Specimen label="Empty">
            <DataTable
              caption="Herd (empty)"
              columns={HERD_COLUMNS}
              rows={[]}
              rowKey={(r) => r.id}
              empty={
                <EmptyState
                  title="No animals enrolled yet"
                  headingLevel={3}
                  icon={ClipboardList}
                  action={
                    <Button variant="primary" icon={ScanLine}>
                      Enroll the first animal
                    </Button>
                  }
                >
                  Enroll an animal from a guided video and its tag appears here.
                </EmptyState>
              }
            />
          </Specimen>
          <Specimen label="Error">
            <DataTable
              caption="Herd (failed)"
              columns={HERD_COLUMNS}
              rows={[]}
              rowKey={(r) => r.id}
              error={<ErrorNotice code="NETWORK_ERROR" onRetry={() => undefined} />}
            />
          </Specimen>
        </div>
      </Section>

      <Section title="Buttons" description="Primary black with a tag-yellow label (48px), secondary and danger outlines (44px), ghost, and the 52px decision size.">
        <div className="flex flex-col gap-6">
          <Specimen label="Default">
            <Row>
              <Button variant="primary" icon={Send}>
                Prepare application
              </Button>
              <Button>Compare products</Button>
              <Button variant="danger" icon={X}>
                Decline
              </Button>
              <Button variant="ghost" icon={Plus}>
                Add a note
              </Button>
            </Row>
          </Specimen>
          <Specimen label="Loading (keeps its label)">
            <Row>
              <Button variant="primary" loading loadingLabel="Approving…">
                Approve and stamp
              </Button>
              <Button loading loadingLabel="Saving…">
                Save note
              </Button>
              <Button variant="danger" loading loadingLabel="Declining…">
                Decline
              </Button>
              <Button variant="primary" loading={loadingDemo} loadingLabel="Approving…" onClick={() => {
                setLoadingDemo(true);
                window.setTimeout(() => setLoadingDemo(false), 1500);
              }}>
                Try loading
              </Button>
            </Row>
          </Specimen>
          <Specimen label="Disabled">
            <Row>
              <Button variant="primary" disabled>
                Approve and stamp
              </Button>
              <Button disabled>Compare products</Button>
              <Button variant="danger" disabled>
                Decline
              </Button>
              <Button variant="ghost" disabled>
                Add a note
              </Button>
            </Row>
          </Specimen>
          <Specimen label="Decision size">
            <div className="flex max-w-[400px] flex-col gap-6 sm:flex-row sm:items-center sm:gap-0">
              <Button variant="primary" size="decision" icon={StampIcon} className="sm:flex-1">
                Approve and stamp
              </Button>
              <Button variant="danger" size="decision" className="sm:ml-8">
                Decline
              </Button>
            </div>
          </Specimen>
          <Specimen label="Icon buttons (44px, always named)">
            <Row>
              <IconButton label="Close" icon={X} />
              <IconButton label="Remove photo" icon={Trash2} variant="secondary" />
              <IconButton label="Close" icon={X} disabled />
              <div className="rounded-control bg-shell p-2" data-surface="shell">
                <IconButton label="Ask" icon={Plus} variant="shell" />
              </div>
            </Row>
          </Specimen>
          <p className="text-sm text-muted">Hover, press, and Tab through these to see hover, active, and focus rings.</p>
        </div>
      </Section>

      <Section title="Status and provenance" description="State is icon plus text plus fill. Provenance is always visible, never behind a hover.">
        <div className="flex flex-col gap-6">
          <Row>
            {TONES.map((t) => (
              <StatusPill key={t.tone} tone={t.tone} label={t.label} />
            ))}
          </Row>
          <Row>
            <Provenance source="live" />
            <Provenance source="prototype" />
            <Provenance source="simulated" />
            <Provenance source="documented" />
          </Row>
        </div>
      </Section>

      <Section title="Figures" description="Every figure, ID, and timestamp in Atkinson Hyperlegible Mono with tabular numerals.">
        <dl className="grid max-w-[960px] grid-cols-1 gap-x-8 lg:grid-cols-2">
          {[
            ["Money", <Money minor={249_600} />],
            ["Range", <Money low={249_600} high={291_200} />],
            ["Exact range", <Money low={249_600} high={291_200} exact />],
            ["Signed debit", <Money minor={-8_736} signed />],
            ["Signed credit", <Money minor={1_000_000} signed />],
            ["Measured range", <Range low={480} high={560} unit="kg" />],
            ["ID", <Mono>animal-demo-002</Mono>],
            ["Timestamp", <Timestamp value={minutesAgo(2)} />],
          ].map(([label, value]) => (
            <div key={label as string} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-line py-3">
              <dt className="text-muted">{label}</dt>
              <dd className="text-end">{value}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="Evidence frames" description="Registered 4:3 frames with the same corner marks for every view. No footage is committed yet, so the missing state is the common case.">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
          <EvidenceFrame view="muzzle" />
          <EvidenceFrame view="teeth" />
          <EvidenceFrame
            view="body"
            src={TEST_CARD}
            alt="Grey test card standing in for the body view"
            capturedAt="2026-10-20T01:12:00Z"
            quality={{ label: "Slight blur", tone: "uncertain" }}
            source="simulated"
          />
        </div>
      </Section>

      <Section
        title="Capture quality meter"
        description="Enroll's live hint: the guide box is sampled every 250 ms and scored for sharpness, light, and steadiness. These meters score synthetic frames. A hint about the picture, never identity confidence."
      >
        <QualitySpecimens />
      </Section>

      <Section title="Drawer" description="A native modal dialog from the right: focus stays inside, Esc closes it, and focus returns to the button.">
        <Button onClick={() => setDrawerOpen(true)}>Open alert drawer</Button>
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          title="Reduced movement"
          description={
            <span>
              <Mono>animal-demo-001</Mono> · cam-pen-a · 09:20–09:42
            </span>
          }
          footer={
            <div className="flex flex-wrap gap-3">
              <Button variant="primary" onClick={() => setDrawerOpen(false)}>
                Acknowledge
              </Button>
              <Button onClick={() => setDrawerOpen(false)}>Add a note</Button>
            </div>
          }
        >
          <div className="flex flex-col gap-4">
            <p>
              Sari moved 38% less than her 7-day baseline over the last 22 minutes. This is an observation, not a diagnosis.
            </p>
            <EvidenceFrame view="body" />
          </div>
        </Drawer>
      </Section>

      <Section title="Loading, empty, and error" description="Skeletons respect reduced motion. Empty states teach what will appear. Errors name the problem and the recovery.">
        <div className="flex flex-col gap-8">
          <div className="grid max-w-[760px] gap-6 sm:grid-cols-2">
            <Specimen label="Skeleton lines">
              <LoadingRegion label="Loading passbook">
                <Skeleton lines={3} />
              </LoadingRegion>
            </Specimen>
            <Specimen label="Skeleton block">
              <Skeleton height="96px" />
            </Specimen>
          </div>
          <EmptyState title="No lines waiting on your stamp" icon={StampIcon} headingLevel={3}>
            When the agent prepares an application, payment, or claim, it waits here until you approve and stamp it or decline
            it.
          </EmptyState>
          <div className="grid gap-3 lg:grid-cols-2">
            {(Object.keys(ERROR_COPY) as ErrorCode[])
              .filter((code) => code !== "IDEMPOTENCY_KEY_REQUIRED")
              .map((code) => (
                <ErrorNotice key={code} code={code} />
              ))}
            <ErrorNotice />
          </div>
        </div>
      </Section>

      <Section title="Toasts" description="Announced through one polite live region.">
        <Row>
          <Button onClick={() => toast.show({ title: "Line 004 stamped and posted", body: "87.36 USD paid to Sandbox Mutual.", tone: "ok" })}>
            Posted
          </Button>
          <Button onClick={() => toast.show({ title: "Payment failed", body: "The sandbox provider timed out. Nothing was charged.", tone: "danger" })}>
            Failed
          </Button>
          <Button onClick={() => toast.show({ title: "Now acting as Operator" })}>Neutral</Button>
        </Row>
      </Section>
    </Page>
  );
}

/** A plain grey test card, honestly labelled as simulated: no footage is committed yet. */
const TEST_CARD =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect width="400" height="300" fill="oklch(0.88 0.004 260)"/><path d="M0 220 Q100 180 200 210 T400 200 V300 H0Z" fill="oklch(0.8 0.006 260)"/><circle cx="300" cy="80" r="28" fill="oklch(0.94 0.003 260)"/></svg>`,
  );
