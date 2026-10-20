import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Lock, RotateCw, Stamp as StampIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { Link, useSearchParams } from "react-router";
import { Button, ButtonLink } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { EmptyState, ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Mono } from "../../components/figures";
import { PageHeader } from "../../components/layout";
import { PassbookLine } from "../../components/PassbookLine";
import { useToast } from "../../components/Toast";
import { tagStateFor } from "../../lib/animal";
import { useRole } from "../../lib/role-store";
import { Page } from "../../pages/Page";
import { ActionReview, actionTitle, useActions, type AgentAction } from "../actions";
import { refreshFinance, useAnimals, useReviseAction } from "../finance/api";
import "./approvals.css";
import { canPrepareAgain, groupActions, lineNumbers, toLine, voidReason, type QueueGroup } from "./queue";
import { WalletPanel } from "./WalletPanel";

const DESKTOP = "(min-width: 64rem)";

function useIsDesktop(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia?.(DESKTOP);
      mq?.addEventListener("change", onChange);
      return () => mq?.removeEventListener("change", onChange);
    },
    () => window.matchMedia?.(DESKTOP).matches ?? true,
    () => true,
  );
}

const FINAL = new Set(["succeeded", "failed", "declined"]);

/** Which lines just reached a final state in this session, so their stamp presses once. */
function usePressed(actions: readonly AgentAction[] | undefined): Set<string> {
  const seen = useRef(new Map<string, string>());
  const pressed = new Set<string>();
  for (const a of actions ?? []) {
    const before = seen.current.get(a.id);
    if (before !== undefined && before !== a.status && FINAL.has(a.status)) pressed.add(a.id);
  }
  useEffect(() => {
    for (const a of actions ?? []) seen.current.set(a.id, a.status);
  });
  return pressed;
}

interface AnimalInfo {
  name: string;
  identity_status: string;
}

function QueueSection({
  group,
  numbers,
  animals,
  selectedId,
  pressed,
}: {
  group: QueueGroup;
  numbers: Map<string, number>;
  animals: Map<string, AnimalInfo>;
  selectedId: string | null;
  pressed: Set<string>;
}) {
  if (group.items.length === 0 && group.id !== "awaiting") return null;
  return (
    <section aria-labelledby={`queue-${group.id}`} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h2 id={`queue-${group.id}`} className="text-lg font-bold">
          {group.title}
        </h2>
        <span className="text-sm text-muted">
          <Mono>{group.items.length}</Mono> {group.items.length === 1 ? "line" : "lines"}
        </span>
      </div>
      <p className="max-w-[70ch] text-muted">{group.description}</p>
      {group.items.length === 0 ? (
        <p className="rounded-control border-2 border-dashed border-line-strong p-4 text-muted">Nothing is waiting for your stamp.</p>
      ) : (
        <ol className="pb-list approval-list border-t border-line">
          {group.items.map((action) => {
            const animal = action.animal_id ? animals.get(action.animal_id) : undefined;
            const line = toLine(action, numbers.get(action.id) ?? 0, pressed.has(action.id));
            const reason = voidReason(action);
            return (
              <PassbookLine
                key={action.id}
                {...line}
                detail={
                  <>
                    <Link
                      to={`?action=${encodeURIComponent(action.id)}`}
                      replace
                      className="approval-link"
                      aria-current={selectedId === action.id ? "true" : undefined}
                    >
                      {animal?.name ?? action.animal_id ?? "Farm"} · to {action.review.recipient}
                    </Link>
                    <span className="block">
                      <Mono>{action.id}</Mono>
                      {action.version > 1 && (
                        <>
                          {" "}
                          · version <Mono>{action.version}</Mono>
                        </>
                      )}
                      {reason && <> · {reason}</>}
                    </span>
                  </>
                }
              />
            );
          })}
        </ol>
      )}
    </section>
  );
}

function ReviewExtras({ action, all, onSelect }: { action: AgentAction; all: readonly AgentAction[]; onSelect: (id: string) => void }) {
  const revise = useReviseAction();
  const toast = useToast();
  const role = useRole();
  const successor = all.find((a) => a.supersedes_id === action.id);
  const stale = action.status === "cancelled" && action.cancel_reason === "approval_stale";
  const animalHref = action.animal_id ? `/animals/${action.animal_id}/insurance` : null;

  const again = () =>
    revise.mutate(action.id, {
      onSuccess: (next) => {
        toast.show({ tone: "ok", title: `${actionTitle(next.action_type)} prepared again — awaiting your stamp` });
        onSelect(next.id);
      },
    });

  return (
    <div className="flex flex-col gap-3">
      {action.status === "succeeded" && action.action_type === "PREMIUM_PAYMENT" && (
        <div className="rounded-control border-2 border-uncertain bg-uncertain-soft p-4">
          <p className="font-bold">Coverage is not active yet</p>
          <p>
            The premium posted to Sandbox Mutual. Cover starts only when the insurer confirms activation.{" "}
            {animalHref && <Link to={animalHref}>See the cover status</Link>}
          </p>
        </div>
      )}
      {action.status === "succeeded" && action.action_type === "POLICY_APPLICATION" && animalHref && (
        <ButtonLink to={animalHref} variant="secondary" icon={ArrowRight}>
          Next: prepare the premium payment
        </ButtonLink>
      )}
      {action.action_type === "CLAIM_SUBMISSION" && action.subject_id && (
        <Link to={`/claims/${action.subject_id}`} className="font-bold">
          Open the claim
        </Link>
      )}
      {successor && (
        <Button variant="secondary" icon={ArrowRight} onClick={() => onSelect(successor.id)}>
          Review version {successor.version}
        </Button>
      )}
      {/* A stale line gets its new version from ActionReview's own "Review the new version". */}
      {!successor && !stale && canPrepareAgain(action) && role.role !== "vet" && (
        <div className="flex flex-col gap-2 border-t border-line pt-3">
          <p className="text-muted">
            {action.status === "expired"
              ? "The approval window closed. The agent can prepare a new version from the current records."
              : "This line is closed. The agent can prepare a new version from the current records."}
          </p>
          {revise.error ? <ErrorNotice error={revise.error} /> : null}
          <div>
            <Button variant="secondary" icon={RotateCw} onClick={again} loading={revise.isPending} loadingLabel="Preparing…">
              {action.status === "expired" ? "Prepare again" : "Prepare a new version"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Review({ action, all, animals, onSelect }: { action: AgentAction; all: readonly AgentAction[]; animals: Map<string, AnimalInfo>; onSelect: (id: string) => void }) {
  const queryClient = useQueryClient();
  const revise = useReviseAction();
  const info = action.animal_id ? animals.get(action.animal_id) : undefined;
  const animal = action.animal_id && info ? { id: action.animal_id, name: info.name, tagState: tagStateFor(info.identity_status) } : undefined;
  return (
    <div className="flex flex-col gap-5">
      <ActionReview
        key={action.id}
        actionId={action.id}
        animal={animal}
        onSettled={() => void refreshFinance(queryClient)}
        onNewVersion={(next) => {
          if (next) onSelect(next);
          else revise.mutate(action.id, { onSuccess: (created) => onSelect(created.id) });
        }}
      />
      {revise.error ? <ErrorNotice error={revise.error} title="A new version couldn't be prepared" /> : null}
      <ReviewExtras action={action} all={all} onSelect={onSelect} />
    </div>
  );
}

export function ApprovalsPage() {
  const role = useRole();
  const isDesktop = useIsDesktop();
  const [params, setParams] = useSearchParams();
  const actions = useActions();
  const animalsQuery = useAnimals();
  const pressed = usePressed(actions.data);
  const selectedId = params.get("action");

  const animals = useMemo(
    () => new Map((animalsQuery.data?.items ?? []).map((a) => [a.id, { name: a.name, identity_status: a.identity_status }])),
    [animalsQuery.data],
  );
  const all = actions.data ?? [];
  const groups = useMemo(() => groupActions(all), [all]);
  const numbers = useMemo(() => lineNumbers(all), [all]);
  const selected = all.find((a) => a.id === selectedId);
  const awaitingCount = groups[0]!.items.length;

  const select = (id: string | null) =>
    setParams(
      (current) => {
        const copy = new URLSearchParams(current);
        if (id) copy.set("action", id);
        else copy.delete("action");
        return copy;
      },
      { replace: true },
    );

  const review = selected ? <Review action={selected} all={all} animals={animals} onSelect={select} /> : null;

  return (
    <Page>
      <PageHeader
        title="Approvals"
        meta={
          <>
            <Mono className="text-ink">{awaitingCount}</Mono> {awaitingCount === 1 ? "line waits" : "lines wait"} for a manager's stamp ·
            everything here runs against the sandbox
          </>
        }
      />
      {role.role !== "manager" && (
        <p className="mb-6 flex items-center gap-3 rounded-control bg-surface-2 p-4">
          <Lock aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
          Only a manager can approve. You can read every line and the wallet; switch role to Manager to stamp.
        </p>
      )}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(380px,460px)] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-10">
          {actions.isPending ? (
            <LoadingRegion label="Loading the approval queue">
              <div className="flex flex-col gap-3">
                <Skeleton height="96px" />
                <Skeleton height="96px" />
                <Skeleton height="96px" />
              </div>
            </LoadingRegion>
          ) : actions.error ? (
            <ErrorNotice error={actions.error} title="The queue couldn't load" onRetry={() => void actions.refetch()} retrying={actions.isRefetching} />
          ) : all.length === 0 ? (
            <EmptyState title="Nothing waits for your stamp" icon={StampIcon}>
              When the agent prepares an application, payment, notification, or claim, it waits here for your stamp.
            </EmptyState>
          ) : (
            groups.map((group) => (
              <QueueSection key={group.id} group={group} numbers={numbers} animals={animals} selectedId={selectedId} pressed={pressed} />
            ))
          )}
          {!isDesktop && <WalletPanel />}
        </div>

        {isDesktop && (
          <aside aria-label="Review and wallet" className="flex min-w-0 flex-col gap-10">
            <div className="rounded-panel border-2 border-ink p-5">
              {review ?? (
                <div className="flex flex-col gap-2">
                  <h2 className="text-md font-bold">Review</h2>
                  <p className="text-muted">
                    {selectedId && !actions.isPending
                      ? "That line isn't on this farm's queue any more."
                      : "Select a line to see exactly what will execute: recipient, amount, terms, evidence, and the balance after."}
                  </p>
                </div>
              )}
            </div>
            <WalletPanel />
          </aside>
        )}
      </div>

      {!isDesktop && (
        <Drawer
          open={Boolean(selected)}
          onClose={() => select(null)}
          title="Review and stamp"
          description={selected ? <Mono>{selected.id}</Mono> : undefined}
        >
          {review}
        </Drawer>
      )}
    </Page>
  );
}
