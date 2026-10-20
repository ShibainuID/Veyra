import { useQuery } from "@tanstack/react-query";
import { Bot, Building2, ChevronDown, Cog, ScrollText, UserRound, type LucideIcon } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { Button } from "../../components/Button";
import { DataTable, type Column } from "../../components/DataTable";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice } from "../../components/feedback";
import { Mono, Timestamp } from "../../components/figures";
import { PageHeader } from "../../components/layout";
import { api } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { humanize, tagStateFor } from "../../lib/animal";
import { cn } from "../../lib/cn";
import { queryKeys, type AuditFilters } from "../../lib/query-keys";
import { Page } from "../../pages/Page";
import { useHerd } from "../passport/api";
import { eventTitle } from "./event-title";

type AuditEvent = components["schemas"]["AuditEventOut"];

const ACTOR: Record<string, { icon: LucideIcon; word: string; className: string }> = {
  agent: { icon: Bot, word: "Agent", className: "bg-tag-soft text-await-ink border border-tag-edge" },
  user: { icon: UserRound, word: "Person", className: "bg-ink text-white" },
  provider: { icon: Building2, word: "Provider", className: "border-2 border-ink text-ink" },
  system: { icon: Cog, word: "System", className: "border-2 border-dashed border-line-strong text-muted" },
};

const SUBJECT_TYPES = ["agent_action", "animal", "enrollment", "valuation", "policy", "alert", "track", "incident", "claim"] as const;

const SUBJECT_WORDS: Record<string, string> = {
  agent_action: "Agent action",
  animal: "Animal",
  enrollment: "Enrollment",
  valuation: "Valuation",
  policy: "Policy",
  alert: "Alert",
  track: "Camera track",
  incident: "Incident",
  claim: "Claim",
};

function subjectWord(type: string): string {
  return SUBJECT_WORDS[type] ?? humanize(type);
}

function subjectLink(event: AuditEvent): string | null {
  switch (event.subject_type) {
    case "alert":
      return `/alerts/${event.subject_id}`;
    case "claim":
      return `/claims/${event.subject_id}`;
    case "animal":
      return `/animals/${event.subject_id}`;
    case "policy":
      return event.animal_id ? `/animals/${event.animal_id}/insurance` : null;
    case "agent_action":
      return "/approvals";
    default:
      return null;
  }
}

/** The one line of context worth reading beside the title: a note, a rationale, a receipt, or an error. */
function eventDetail(event: AuditEvent): string | null {
  const d = event.data;
  const pick = (value: unknown) => (typeof value === "string" && value ? value : null);
  const receipt = d.receipt && typeof d.receipt === "object" ? (d.receipt as Record<string, unknown>) : null;
  const ref = receipt ? ["payment_ref", "application_ref", "notification_ref", "claim_ref"].map((k) => pick(receipt[k])).find(Boolean) : null;
  const error = d.error && typeof d.error === "object" ? pick((d.error as Record<string, unknown>).code) : null;
  return pick(d.note) ?? pick(d.rationale) ?? (ref ? `Receipt ${ref}` : null) ?? error ?? (pick(d.cancel_reason)?.replace(/_/g, " ") ?? null);
}

function ActorCell({ event }: { event: AuditEvent }) {
  const style = ACTOR[event.actor.type] ?? ACTOR.system!;
  const Icon = style.icon;
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      <span className={cn("inline-flex h-8 flex-none items-center gap-1.5 rounded-pill px-2.5 text-sm font-bold", style.className)}>
        <Icon aria-hidden="true" className="size-4" strokeWidth={2.25} />
        {style.word}
      </span>
      <span className="min-w-0 truncate">{event.actor.name}</span>
    </span>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm font-bold text-muted">{label}</span>
      <span className="relative">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-11 w-full min-w-56 cursor-pointer appearance-none rounded-control border-2 border-line-strong bg-bg py-2 pr-10 pl-3 font-bold hover:border-ink focus:border-ink"
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 size-5 -translate-y-1/2" strokeWidth={2.25} />
      </span>
    </label>
  );
}

export function AuditPage() {
  const [params, setParams] = useSearchParams();
  const filters: AuditFilters = {};
  const animalId = params.get("animal") ?? "";
  const subjectType = params.get("subject") ?? "";
  if (animalId) filters.animal_id = animalId;
  if (subjectType) filters.subject_type = subjectType;

  const herd = useHerd({});
  const animals = useMemo(() => new Map((herd.data?.items ?? []).map((item) => [item.id, item])), [herd.data]);

  const audit = useQuery({
    queryKey: queryKeys.audit(filters),
    queryFn: async () => {
      const { data } = await api.GET("/api/v1/audit-events", { params: { query: { ...filters, limit: 200 } } });
      return [...(data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
    },
    placeholderData: (previous) => previous,
  });

  const update = (key: string, value: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });

  const columns: Column<AuditEvent>[] = [
    {
      id: "animal",
      header: "Animal",
      width: "88px",
      lead: true,
      cell: (event) => {
        if (!event.animal_id) return <span className="text-sm text-muted">Farm</span>;
        const animal = animals.get(event.animal_id);
        return (
          <Link to={`/animals/${event.animal_id}`} aria-label={`Passport for ${animal?.name ?? event.animal_id}`} className="inline-block rounded-control">
            <EarTag animalId={event.animal_id} state={tagStateFor(animal?.identity_status ?? "confirmed")} />
          </Link>
        );
      },
    },
    {
      id: "time",
      header: "Time",
      width: "196px",
      cell: (event) => (
        <span className="flex flex-col">
          <Timestamp value={event.created_at} mode="absolute" />
          <Timestamp value={event.created_at} mode="relative" className="text-sm text-muted" />
        </span>
      ),
    },
    { id: "actor", header: "Actor", width: "236px", cell: (event) => <ActorCell event={event} /> },
    {
      id: "event",
      header: "Event",
      cell: (event) => {
        const detail = eventDetail(event);
        return (
          <span className="flex min-w-0 flex-col">
            <span className="font-bold">{eventTitle(event.event_type, event.data)}</span>
            {detail && <span className="text-sm text-muted">{detail}</span>}
          </span>
        );
      },
    },
    {
      id: "subject",
      header: "Subject",
      width: "220px",
      cell: (event) => {
        const href = subjectLink(event);
        return (
          <span className="flex min-w-0 flex-col">
            <span className="text-sm text-muted">{subjectWord(event.subject_type)}</span>
            {href ? (
              <Link to={href} className="figures truncate text-sm font-bold">
                {event.subject_id}
              </Link>
            ) : (
              <Mono className="truncate text-sm">{event.subject_id}</Mono>
            )}
          </span>
        );
      },
    },
  ];

  const filtered = Boolean(animalId || subjectType);

  return (
    <Page>
      <PageHeader title="Audit" meta="Every proposal, decision, and provider result, recorded separately and in order." />
      <div className="mb-6 flex flex-wrap items-end gap-4">
        <Select
          label="Animal"
          value={animalId}
          onChange={(value) => update("animal", value)}
          options={[
            { value: "", label: "All animals" },
            ...[...animals.values()].map((animal) => ({ value: animal.id, label: `${animal.name} · ${animal.id}` })),
          ]}
        />
        <Select
          label="Subject"
          value={subjectType}
          onChange={(value) => update("subject", value)}
          options={[{ value: "", label: "All subjects" }, ...SUBJECT_TYPES.map((type) => ({ value: type, label: subjectWord(type) }))]}
        />
        {filtered && (
          <Button variant="ghost" onClick={() => setParams(new URLSearchParams())}>
            Clear filters
          </Button>
        )}
      </div>
      <DataTable
        caption="Audit events, newest first"
        columns={columns}
        rows={audit.data ?? []}
        rowKey={(event) => event.id}
        loading={audit.isPending}
        loadingRows={8}
        error={
          audit.error ? (
            <ErrorNotice error={audit.error} title="The audit log couldn't load" onRetry={() => void audit.refetch()} retrying={audit.isRefetching} />
          ) : undefined
        }
        empty={
          <EmptyState title={filtered ? "No events match these filters" : "Nothing recorded yet"} icon={ScrollText}>
            {filtered
              ? "Try another animal or subject, or clear the filters."
              : "Enrollment, valuations, the agent's proposals, decisions, and provider results each record an event here."}
          </EmptyState>
        }
      />
    </Page>
  );
}
