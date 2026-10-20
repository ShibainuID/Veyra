import { FileCheck2, FilePlus2, Lock } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { Button } from "../../components/Button";
import { DataTable, type Column } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Money, Mono, Timestamp } from "../../components/figures";
import { PageHeader } from "../../components/layout";
import { StatusPill } from "../../components/StatusPill";
import { tagStateFor } from "../../lib/animal";
import { useRole } from "../../lib/role-store";
import { Page } from "../../pages/Page";
import { useAnimals, type AnimalRow, type Claim } from "../finance/api";
import { useClaims } from "./api";
import { IncidentForm } from "./IncidentForm";
import { checklistLabel, claimStatus } from "./labels";

export function ClaimsPage() {
  const role = useRole();
  const [params, setParams] = useSearchParams();
  const claims = useClaims();
  const animals = useAnimals();
  const canRecord = role.role !== "vet";
  // The alert drawer links here with ?animal=…&alert=… (and ?record=1 opens the form directly).
  const prefillAnimal = params.get("animal") ?? undefined;
  const prefillAlert = params.get("alert") ?? undefined;
  const open = canRecord && (params.get("record") === "1" || Boolean(prefillAnimal) || Boolean(prefillAlert));

  const setOpen = (next: boolean) => {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current);
        if (next) copy.set("record", "1");
        else ["record", "animal", "alert"].forEach((key) => copy.delete(key));
        return copy;
      },
      { replace: true },
    );
  };

  const byId = useMemo(() => new Map((animals.data?.items ?? []).map((a) => [a.id, a])), [animals.data]);

  const columns: Column<Claim>[] = [
    {
      id: "tag",
      header: "Tag",
      width: "88px",
      lead: true,
      cell: (c) => <EarTag animalId={c.animal_id} state={tagStateFor(byId.get(c.animal_id)?.identity_status)} />,
    },
    {
      id: "claim",
      header: "Claim",
      primary: true,
      sortValue: (c) => byId.get(c.animal_id)?.name ?? c.animal_id,
      cell: (c) => (
        <span className="flex flex-col">
          <span>{byId.get(c.animal_id)?.name ?? c.animal_id}</span>
          <Mono className="text-sm text-muted">{c.id}</Mono>
        </span>
      ),
    },
    {
      id: "status",
      header: "Status",
      sortValue: (c) => c.status,
      cell: (c) => {
        const s = claimStatus(c.status);
        return <StatusPill tone={s.tone} label={s.label} />;
      },
    },
    {
      id: "missing",
      header: "Evidence",
      cell: (c) =>
        c.missing.length === 0 ? (
          <span className="text-muted">All on file</span>
        ) : (
          <span>
            Missing: {c.missing.map(checklistLabel).join(", ").toLowerCase()}
          </span>
        ),
    },
    {
      id: "amount",
      header: "Claimed",
      align: "end",
      sortValue: (c) => c.claimed_amount_minor,
      cell: (c) => <Money minor={c.claimed_amount_minor} currency={c.currency} className="font-bold" />,
    },
    {
      id: "updated",
      header: "Updated",
      sortValue: (c) => c.updated_at,
      cell: (c) => <Timestamp value={c.updated_at} mode="relative" />,
    },
  ];

  const animalRows: AnimalRow[] = animals.data?.items ?? [];

  return (
    <Page>
      <PageHeader
        title="Claims"
        meta="Incidents and their sandbox claim submissions. A claim is drafted from a recorded incident, never from an alert alone."
        actions={
          canRecord ? (
            <Button variant="primary" icon={FilePlus2} onClick={() => setOpen(true)}>
              Record incident
            </Button>
          ) : (
            <span className="flex items-center gap-2 text-muted">
              <Lock aria-hidden="true" className="size-4" strokeWidth={2.25} />A manager or operator records incidents.
            </span>
          )
        }
      />

      <DataTable
        caption="Claims on this farm"
        columns={columns}
        rows={claims.data ?? []}
        rowKey={(c) => c.id}
        rowHref={(c) => `/claims/${c.id}`}
        defaultSort={{ columnId: "updated", direction: "descending" }}
        loading={claims.isPending}
        error={claims.error ? <ErrorNotice error={claims.error} onRetry={() => void claims.refetch()} retrying={claims.isRefetching} /> : undefined}
        empty={
          <EmptyState title="No claims yet" icon={FileCheck2} headingLevel={3}>
            When something happens to an insured animal, record the incident here. VEYRA drafts the claim with its evidence
            checklist, and a manager stamps the submission.
          </EmptyState>
        }
      />

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="Record incident"
        description="The farm's report of what happened. A vet's assessment and camera observations are kept separately."
      >
        {open && animals.isPending && (
          <LoadingRegion label="Loading the herd">
            <Skeleton lines={6} />
          </LoadingRegion>
        )}
        {open && animals.error ? <ErrorNotice error={animals.error} onRetry={() => void animals.refetch()} /> : null}
        {open && animals.data && (
          <IncidentForm animals={animalRows} initialAnimalId={prefillAnimal} initialAlertId={prefillAlert} onDone={() => setOpen(false)} />
        )}
      </Drawer>
    </Page>
  );
}
