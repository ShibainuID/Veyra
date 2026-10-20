import { ScanLine, Search, SearchX, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Button, ButtonLink } from "../../components/Button";
import type { Column } from "../../components/DataTable";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice } from "../../components/feedback";
import { Money, Mono, Timestamp } from "../../components/figures";
import { FilterChips, type FilterOption } from "../../components/FilterChips";
import { PageHeader } from "../../components/layout";
import { Provenance, type Source } from "../../components/Provenance";
import { StatusPill } from "../../components/StatusPill";
import { useShellSummary } from "../../app/use-shell-summary";
import { asSource, coveragePill, healthPill, identityPill, productName, tagStateFor } from "../../lib/animal";
import { formatMoney, formatMoneyRange } from "../../lib/format";
import type { HerdFilters } from "../../lib/query-keys";
import { useMediaQuery } from "../../lib/use-media-query";
import { AnimalPassbook } from "../passbook/AnimalPassbook";
import { useHerd, type HerdItem } from "../passport/api";

export type HerdFilter = "all" | "uncovered" | "alerts" | "awaiting" | "identity";

const FILTERS: readonly HerdFilter[] = ["all", "uncovered", "alerts", "awaiting", "identity"];

const FILTER_LABEL: Record<HerdFilter, string> = {
  all: "All",
  uncovered: "Not covered",
  alerts: "Open alerts",
  awaiting: "Awaiting approval",
  identity: "Identity review",
};

/** Server filters where the API has them; awaiting and identity are narrowed on the client. */
export function serverFilters(filter: HerdFilter, q: string): HerdFilters {
  const filters: HerdFilters = {};
  if (filter === "uncovered") filters.coverage = "none";
  if (filter === "alerts") filters.alerts = "open";
  if (q.trim()) filters.q = q.trim();
  return filters;
}

export function matchesFilter(item: HerdItem, filter: HerdFilter): boolean {
  switch (filter) {
    case "uncovered":
      return item.coverage.status === "none";
    case "alerts":
      return item.alerts.open_count > 0;
    case "awaiting":
      return item.awaiting_approval_count > 0;
    case "identity":
      return item.identity_status !== "confirmed";
    default:
      return true;
  }
}

function asFilter(value: string | null): HerdFilter {
  return value && (FILTERS as readonly string[]).includes(value) ? (value as HerdFilter) : "all";
}

/** Alert kinds short enough for the herd's Alerts column; the alert page carries the full wording. */
function shortAlertLabel(kind: string): string {
  if (kind === "reduced_movement") return "Movement";
  if (kind === "observation_quality") return "Quality";
  return "Alert";
}

/** Sorts the most urgent health state last, so a descending sort puts it on top. */
const HEALTH_ORDER: readonly HerdItem["health"]["status"][] = [
  "not_monitored",
  "normal",
  "veterinary_reviewed",
  "observation_gap",
  "under_review",
  "needs_inspection",
];

const COLUMNS: readonly Column<HerdItem>[] = [
  {
    id: "tag",
    header: "Tag",
    width: "76px",
    lead: true,
    sortValue: (row) => row.id,
    cell: (row) => <EarTag animalId={row.id} state={tagStateFor(row.identity_status)} />,
  },
  {
    id: "animal",
    header: "Animal",
    primary: true,
    sortValue: (row) => row.name,
    cell: (row) => (
      <span className="flex min-w-0 flex-col">
        <span>{row.name}</span>
        <span className="flex flex-col text-sm font-regular text-muted">
          {/* Below xl the tag's printed number carries the ID, so the row keeps to 64px. */}
          <Mono className="hidden whitespace-nowrap xl:inline">{row.id}</Mono>
          <span>{row.breed}</span>
        </span>
      </span>
    ),
  },
  {
    id: "identity",
    header: "Identity",
    width: "124px",
    sortValue: (row) => row.identity_status,
    cell: (row) => <StatusPill {...identityPill(row.identity_status)} />,
  },
  {
    id: "exposure",
    header: "Exposure",
    width: "156px",
    sortValue: (row) => row.valuation?.value_high_minor ?? null,
    cell: (row) => <ExposureCell row={row} columnSource={null} />,
  },
  {
    id: "coverage",
    header: "Coverage",
    width: "136px",
    sortValue: (row) => row.coverage.status,
    cell: (row) => (
      <span className="flex flex-col items-start gap-1">
        <StatusPill {...coveragePill(row.coverage.status)} />
        {row.coverage.product_id && (
          <span className="max-w-28 truncate text-sm text-muted max-md:max-w-none max-md:whitespace-normal xl:max-w-none xl:whitespace-normal" title={productName(row.coverage.product_id) ?? undefined}>
            {productName(row.coverage.product_id)}
          </span>
        )}
      </span>
    ),
  },
  {
    id: "observed",
    header: "Last observed",
    width: "124px",
    sortValue: (row) => row.last_observation?.observed_at ?? null,
    cell: (row) =>
      row.last_observation ? (
        <span className="flex flex-col">
          <Timestamp value={row.last_observation.observed_at} mode="relative" />
          <span className="text-sm text-muted">{row.last_observation.camera_name ?? row.last_observation.camera_id}</span>
        </span>
      ) : (
        <span className="text-sm text-muted">No camera observation</span>
      ),
  },
  {
    id: "health",
    header: "Health",
    width: "172px",
    sortValue: (row) => HEALTH_ORDER.indexOf(row.health.status) * 100 + row.awaiting_approval_count,
    cell: (row) => (
      <span className="flex flex-col items-start gap-1" title={row.health.reason}>
        <StatusPill {...healthPill(row.health.status)} />
        {row.alerts.open_count > 0 && (
          <span className="text-sm text-muted">
            {row.alerts.kinds.length > 0 ? row.alerts.kinds.map(shortAlertLabel).join(", ") : "Alert"} alert open
          </span>
        )}
        {row.awaiting_approval_count > 0 && (
          <StatusPill tone="awaiting" label={row.awaiting_approval_count === 1 ? "Awaiting" : `${row.awaiting_approval_count} awaiting`} />
        )}
      </span>
    ),
  },
];

/** The weight source most rows share: the Exposure column prints it once in its header. */
export function columnSource(rows: readonly HerdItem[]): Source | null {
  const counts = new Map<Source, number>();
  for (const row of rows) {
    if (!row.valuation || !row.weight) continue;
    const source = asSource(row.weight.source);
    counts.set(source, (counts.get(source) ?? 0) + 1);
  }
  let best: Source | null = null;
  for (const [source, count] of counts) if (!best || count > (counts.get(best) ?? 0)) best = source;
  return best;
}

function ExposureCell({ row, columnSource }: { row: HerdItem; columnSource: Source | null }) {
  if (!row.valuation) return <span className="text-muted">Not valued</span>;
  const source = row.weight ? asSource(row.weight.source) : null;
  const differs = source !== null && source !== columnSource;
  return (
    <span className="flex flex-col items-start gap-1">
      <Money
        low={row.valuation.value_low_minor}
        high={row.valuation.value_high_minor}
        currency={row.valuation.currency}
        className="font-bold whitespace-nowrap"
      />
      {/* A row whose source differs from the column's carries its own chip; stacked rows (no header) always do. */}
      {source && <Provenance source={source} className={differs ? undefined : "dt-stacked-only"} />}
    </span>
  );
}

function HerdMeta() {
  const { data: summary } = useShellSummary();
  if (!summary) return <span>Every tagged animal, its exposure, and its cover.</span>;
  const { currency } = summary;
  return (
    <span className="flex flex-wrap gap-x-2 gap-y-1">
      <span>
        <Mono className="text-ink">{summary.animal_count}</Mono> {summary.animal_count === 1 ? "animal" : "animals"}
      </span>
      <span aria-hidden="true">·</span>
      <span>
        indicative exposure <Mono className="text-ink">{formatMoneyRange(summary.exposure_low_minor, summary.exposure_high_minor, currency)}</Mono>
      </span>
      <span aria-hidden="true">·</span>
      <span>
        insured <Mono className="text-ink">{formatMoney(summary.insured_minor, currency, { whole: true })}</Mono>
      </span>
      <span aria-hidden="true">·</span>
      <span className={summary.uncovered_count > 0 ? "font-bold text-danger" : undefined}>
        <Mono>{summary.uncovered_count}</Mono> uncovered
      </span>
    </span>
  );
}

export function HerdPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const filter = asFilter(params.get("filter"));
  const q = params.get("q") ?? "";
  const selectedParam = params.get("animal");
  const wide = useMediaQuery("(min-width: 64rem)");
  const roomy = useMediaQuery("(min-width: 80rem)");
  const [draft, setDraft] = useState(q);

  // Debounce the search field into the URL, so a search can be shared and survives reload.
  useEffect(() => setDraft(q), [q]);
  useEffect(() => {
    if (draft === q) return;
    const id = window.setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (draft.trim()) next.set("q", draft);
          else next.delete("q");
          return next;
        },
        { replace: true },
      );
    }, 250);
    return () => window.clearTimeout(id);
  }, [draft, q, setParams]);

  const herd = useHerd(serverFilters(filter, q));
  const all = useHerd({});
  const rows = useMemo(() => (herd.data?.items ?? []).filter((item) => matchesFilter(item, filter)), [herd.data, filter]);
  const source = columnSource(rows);
  // Beside the passbook on a tablet, the tag's solid or dashed outline already says the identity
  // state and the passbook carries the last observation, so those columns step aside below xl.
  const columns = useMemo(
    () =>
      COLUMNS.filter((column) => roomy || (column.id !== "identity" && column.id !== "observed")).map((column) =>
        column.id === "exposure" && source
          ? {
              ...column,
              cell: (row: HerdItem) => <ExposureCell row={row} columnSource={source} />,
              headerAddon: <Provenance source={source} />,
              headerDescription: `Every exposure in this column is ${source} unless its row says otherwise`,
            }
          : column,
      ),
    [roomy, source],
  );

  const options: FilterOption<HerdFilter>[] = FILTERS.map((value) => ({
    value,
    label: FILTER_LABEL[value],
    count: all.data ? all.data.items.filter((item) => matchesFilter(item, value)).length : undefined,
  }));

  const defaultSelection = rows.find((row) => row.awaiting_approval_count > 0)?.id ?? rows[0]?.id ?? null;
  // Hold on to the default once shown: stamping its waiting line must not swap the panel to
  // another animal mid-press, which would hide the stamp landing.
  const [pinned, setPinned] = useState<string | null>(null);
  useEffect(() => {
    if (!pinned && defaultSelection) setPinned(defaultSelection);
  }, [pinned, defaultSelection]);
  // A pinned animal that left the herd (a demo reset) gives way to the default again.
  useEffect(() => {
    if (pinned && all.data && !all.data.items.some((item) => item.id === pinned)) setPinned(null);
  }, [pinned, all.data]);
  const panelAnimal = selectedParam ?? pinned ?? defaultSelection;

  const hrefFor = (animalId: string) => {
    const next = new URLSearchParams(params);
    next.set("animal", animalId);
    return `/?${next.toString()}`;
  };

  const setFilter = (value: HerdFilter) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === "all") next.delete("filter");
      else next.set("filter", value);
      return next;
    });

  const clearFilters = () => {
    setDraft("");
    setParams((prev) => {
      const next = new URLSearchParams();
      const animal = prev.get("animal");
      if (animal) next.set("animal", animal);
      return next;
    });
  };

  const closeDrawer = () => {
    const next = new URLSearchParams(params);
    next.delete("animal");
    const search = next.toString();
    navigate(search ? `/?${search}` : "/", { replace: true });
  };

  const drawerItem = (herd.data?.items ?? []).find((row) => row.id === selectedParam);

  return (
    <div className="flex flex-1">
      <div className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-4 lg:py-8 xl:px-6">
        <PageHeader
          title="Herd"
          meta={<HerdMeta />}
          actions={
            <ButtonLink to="/enroll" variant="secondary" icon={ScanLine}>
              Enroll an animal
            </ButtonLink>
          }
        />
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <FilterChips label="Filter herd" options={options} value={filter} onChange={setFilter} />
          <label className="relative block w-full sm:w-72">
            <span className="sr-only">Search by tag or name</span>
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-muted" strokeWidth={2.25} />
            <input
              type="search"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Search by tag or name"
              className="min-h-11 w-full rounded-control border-2 border-line-strong bg-bg py-2 pr-3 pl-10 placeholder:text-muted hover:border-ink focus:border-ink"
            />
          </label>
        </div>
        <DataTable
          caption="Herd: each animal's tag, identity, indicative exposure, cover, last observation, and alerts"
          columns={columns}
          stack="narrow"
          rows={rows}
          rowKey={(row) => row.id}
          rowHref={(row) => hrefFor(row.id)}
          selectedKey={wide ? panelAnimal : selectedParam}
          loading={herd.isPending}
          loadingRows={6}
          className="overflow-x-auto"
          error={
            herd.error ? (
              <ErrorNotice error={herd.error} title="The herd couldn't load" onRetry={() => void herd.refetch()} retrying={herd.isRefetching} />
            ) : undefined
          }
          empty={
            <EmptyState
              title="No animals match these filters"
              icon={SearchX}
              action={
                <Button variant="secondary" icon={X} onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            >
              {q ? (
                <>
                  Nothing matches <Mono className="text-ink">{q}</Mono>
                  {filter !== "all" ? ` under ${FILTER_LABEL[filter]}` : ""}. Search by tag number, ID, or name.
                </>
              ) : (
                `No animal is in ${FILTER_LABEL[filter]} right now.`
              )}
            </EmptyState>
          }
        />
      </div>

      {wide && (
        <aside
          aria-label="Selected animal's passbook"
          className="sticky top-(--shell-height) flex h-[calc(100dvh-var(--shell-height))] w-(--passbook-width) flex-none flex-col border-l-2 border-ink"
        >
          {panelAnimal ? (
            <AnimalPassbook key={panelAnimal} animalId={panelAnimal} passportLink className="h-full" />
          ) : (
            <div className="p-5">
              <EmptyState title="No animal selected" headingLevel={2}>
                Select a row to open that tag's passbook here.
              </EmptyState>
            </div>
          )}
        </aside>
      )}

      {!wide && (
        <Drawer
          open={Boolean(selectedParam)}
          onClose={closeDrawer}
          title={drawerItem ? `${drawerItem.name}'s passbook` : "Passbook"}
          bodyClassName=""
        >
          {selectedParam && <AnimalPassbook key={selectedParam} animalId={selectedParam} headingLevel={3} passportLink />}
        </Drawer>
      )}
    </div>
  );
}
