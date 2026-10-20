import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import { DataTable, type Column } from "../../components/DataTable";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice } from "../../components/feedback";
import { FilterChips } from "../../components/FilterChips";
import { Mono, Timestamp } from "../../components/figures";
import { StatusPill } from "../../components/StatusPill";
import { KIND_LABEL, STATUS_LABEL, STATUS_TONE, alertSubject, type AlertStatus, type AlertView } from "./alert-copy";
import "./alerts.css";

/** Keeps Monitor's query (scenario, animal) when an alert opens and closes. */
export function useAlertHref() {
  const { search } = useLocation();
  return (id: string) => `/alerts/${encodeURIComponent(id)}${search}`;
}

function Subject({ alert }: { alert: AlertView }) {
  return (
    <span className="flex min-w-0 items-center gap-3">
      {alert.animal_id ? <EarTag animalId={alert.animal_id} state="confirmed" size="sm" /> : <EarTag state="none" size="sm" />}
      <span className="min-w-0">
        <span className="block truncate font-bold">{alertSubject(alert)}</span>
        <span className="block text-sm text-muted">{KIND_LABEL[alert.kind]}</span>
      </span>
    </span>
  );
}

/**
 * The live feed beside the stage: newest first. Alerts that arrive while the page is open slide in once; the
 * ones already there when it opened do not move.
 */
export function AlertFeed({ alerts, loading }: { alerts: readonly AlertView[]; loading: boolean }) {
  const href = useAlertHref();
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (loading) return;
    if (seen.current === null) {
      seen.current = new Set(alerts.map((a) => a.id));
      return;
    }
    const arrived = alerts.filter((a) => !seen.current!.has(a.id)).map((a) => a.id);
    if (arrived.length === 0) return;
    arrived.forEach((id) => seen.current!.add(id));
    setFresh((prev) => new Set([...prev, ...arrived]));
  }, [alerts, loading]);

  if (!loading && alerts.length === 0) {
    return <p className="py-3 text-muted">No open alerts. New ones post here the moment a rule trips.</p>;
  }
  return (
    <ol className="flex flex-col gap-2" aria-live="polite" aria-relevant="additions">
      {alerts.slice(0, 6).map((alert) => (
        <li key={alert.id} className="alert-feed-item" data-fresh={fresh.has(alert.id) ? "" : undefined}>
          <Link
            to={href(alert.id)}
            className="flex min-h-16 items-center gap-3 rounded-control border-2 border-line px-3 py-2 no-underline hover:border-ink hover:bg-surface"
          >
            <span className="min-w-0 flex-1">
              <Subject alert={alert} />
              <span className="mt-1 block text-sm text-muted">
                {alert.camera_name} · <Timestamp value={alert.window_start} mode="absolute" />
              </span>
            </span>
            <span className="flex flex-none flex-col items-end gap-1">
              <StatusPill tone={STATUS_TONE[alert.status]} label={STATUS_LABEL[alert.status]} />
              <ChevronRight aria-hidden="true" className="size-5 text-muted" strokeWidth={2.25} />
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

type Filter = AlertStatus | "all";

export function AlertsTable({ alerts, loading, error, onRetry }: { alerts: readonly AlertView[]; loading: boolean; error: unknown; onRetry: () => void }) {
  const [filter, setFilter] = useState<Filter>("open");
  const href = useAlertHref();
  const { pathname } = useLocation();
  const selectedId = pathname.startsWith("/alerts/") ? decodeURIComponent(pathname.slice("/alerts/".length)) : null;
  const counts = useMemo(() => {
    const c: Record<Filter, number> = { open: 0, acknowledged: 0, resolved: 0, all: alerts.length };
    alerts.forEach((a) => (c[a.status] += 1));
    return c;
  }, [alerts]);
  const rows = filter === "all" ? alerts : alerts.filter((a) => a.status === filter);
  const columns: Column<AlertView>[] = [
    { id: "subject", header: "Animal", cell: (a) => <Subject alert={a} />, primary: true, sortValue: (a) => alertSubject(a) },
    { id: "camera", header: "Camera", cell: (a) => a.camera_name, sortValue: (a) => a.camera_name },
    {
      id: "window",
      header: "Window",
      cell: (a) => <Timestamp value={a.window_start} />,
      sortValue: (a) => a.window_start,
    },
    {
      id: "status",
      header: "Status",
      cell: (a) => <StatusPill tone={STATUS_TONE[a.status]} label={STATUS_LABEL[a.status]} />,
      sortValue: (a) => a.status,
    },
    { id: "id", header: "Alert", cell: (a) => <Mono className="text-sm text-muted">{a.id}</Mono>, align: "end" },
  ];
  return (
    <div className="flex flex-col gap-4">
      <FilterChips
        label="Filter alerts by status"
        value={filter}
        onChange={setFilter}
        options={[
          { value: "open", label: "Open", count: counts.open },
          { value: "acknowledged", label: "Acknowledged", count: counts.acknowledged },
          { value: "resolved", label: "Resolved", count: counts.resolved },
          { value: "all", label: "All", count: counts.all },
        ]}
      />
      <DataTable
        caption="Alerts"
        columns={columns}
        rows={rows}
        rowKey={(a) => a.id}
        rowHref={(a) => href(a.id)}
        selectedKey={selectedId}
        loading={loading}
        defaultSort={{ columnId: "window", direction: "descending" }}
        error={error ? <ErrorNotice error={error} onRetry={onRetry} /> : undefined}
        empty={
          <EmptyState title={filter === "all" ? "No alerts on this farm" : `No ${STATUS_LABEL[filter as AlertStatus].toLowerCase()} alerts`} headingLevel={3}>
            Alerts are raised by the movement and observation-quality rules as camera windows close.
          </EmptyState>
        }
      />
    </div>
  );
}
