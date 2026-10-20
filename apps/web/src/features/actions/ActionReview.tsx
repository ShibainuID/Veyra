import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Lock, RefreshCw, RotateCw, Send, Stamp as StampIcon } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Button } from "../../components/Button";
import { EarTag, type EarTagState } from "../../components/EarTag";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Money, Mono } from "../../components/figures";
import { Stamp } from "../../components/Stamp";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { request } from "../../lib/api";
import { providerName, tagStateFor } from "../../lib/animal";
import { cn } from "../../lib/cn";
import { toApiError } from "../../lib/errors";
import { formatCountdown, lineNumber } from "../../lib/format";
import { queryKeys } from "../../lib/query-keys";
import { useRole } from "../../lib/role-store";
import { useNow } from "../../lib/use-now";
import { fetchAction, invalidateAfterAction, useAction, useActionDecision, useExecuteAction } from "./hooks";
import { outcomeToast, receiptRef } from "./outcome";
import { actionTitle, type AgentAction } from "./types";

export interface ActionReviewAnimal {
  id: string;
  name: string;
  tagState: EarTagState;
}

export interface ActionReviewProps {
  actionId: string;
  /**
   * "full" (Approvals, a dedicated review) prints every field and the evidence list open.
   * "bar" (the passbook's awaiting line) keeps the summary tight and folds the evidence.
   */
  variant?: "full" | "bar";
  /** The passbook line this action waits on, for "Balance after line 004". */
  lineNo?: number;
  /** Known animal details; otherwise they are read from the herd list. */
  animal?: ActionReviewAnimal;
  /** Called with the replacing action's ID after "Review the new version". */
  onNewVersion?: (actionId: string | null) => void;
  /** Called after the action reaches a final state from this review. */
  onSettled?: (action: AgentAction) => void;
  className?: string;
}

const BLOCKING_CODES = new Set(["APPROVAL_STALE", "ACTION_EXPIRED", "FORBIDDEN_ROLE", "IDENTITY_UNCONFIRMED"]);

interface HerdIndexItem {
  id: string;
  name: string;
  identity_status: string;
}

function useAnimalFromHerd(animalId: string | null | undefined, known?: ActionReviewAnimal): ActionReviewAnimal | null {
  const { data } = useQuery({
    queryKey: queryKeys.animals,
    queryFn: () => request<{ items: HerdIndexItem[] }>("/animals"),
    enabled: Boolean(animalId) && !known,
    staleTime: 30_000,
  });
  if (known) return known;
  if (!animalId) return null;
  const item = (data?.items as HerdIndexItem[] | undefined)?.find((row) => row.id === animalId);
  return { id: animalId, name: item?.name ?? animalId, tagState: tagStateFor(item?.identity_status) };
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="pt-0.5 text-sm text-muted">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

/**
 * The version to review instead of a stale or expired one: an open action that already
 * supersedes it, else a fresh one prepared from current records (`revise`). Null if neither works.
 */
async function findNewVersion(action: AgentAction): Promise<string | null> {
  try {
    const query = new URLSearchParams();
    if (action.animal_id) query.set("animal_id", action.animal_id);
    const { items } = await request<{ items: AgentAction[] }>(`/agent/actions?${query.toString()}`);
    const successor = items.find(
      (item) => item.id !== action.id && item.status === "pending_approval" && item.supersedes_id === action.id,
    );
    if (successor) return successor.id;
  } catch {
    // Fall through to preparing a new version.
  }
  try {
    const revised = await request<AgentAction>(`/agent/actions/${encodeURIComponent(action.id)}/revise`, { method: "POST" });
    return revised.id;
  } catch {
    return null;
  }
}

/**
 * The review of one agent action: exactly what will execute, who receives it, and what it leaves
 * in the wallet, then the manager's decision. "Approve and stamp" records the approval and runs
 * the action with one Idempotency-Key; Decline sits apart and takes an optional note.
 */
export function ActionReview({ actionId, variant = "full", lineNo, animal, onNewVersion, onSettled, className }: ActionReviewProps) {
  const headingId = useId();
  const noteId = useId();
  const queryClient = useQueryClient();
  const toast = useToast();
  const role = useRole();
  const { data: action, isPending, error: loadError, refetch, isRefetching } = useAction(actionId);
  const decision = useActionDecision();
  const execute = useExecuteAction();
  const now = useNow(1000, action?.status === "pending_approval");
  const [declineOpen, setDeclineOpen] = useState(false);
  const [note, setNote] = useState("");
  const [running, setRunning] = useState<"approve" | "execute" | "decline" | null>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const resolvedAnimal = useAnimalFromHerd(action?.animal_id, animal);

  if (isPending) {
    return (
      <LoadingRegion label="Loading what this action will do">
        <div className={cn("flex flex-col gap-3", className)}>
          <Skeleton lines={3} />
          <Skeleton height="52px" />
        </div>
      </LoadingRegion>
    );
  }
  if (loadError || !action) {
    return <ErrorNotice error={loadError} title="This action couldn't load" onRetry={() => void refetch()} retrying={isRefetching} className={className} />;
  }

  const title = actionTitle(action.action_type);
  const review = action.review;
  const currency = review.currency ?? "USD";
  const isManager = role.role === "manager";
  const expiresMs = new Date(action.expires_at).getTime() - now;
  const expiredLocally = action.status === "pending_approval" && expiresMs <= 0;
  const mutationError = decision.error ?? execute.error;
  const apiError = toApiError(mutationError);
  const blockingCode =
    apiError && BLOCKING_CODES.has(apiError.code)
      ? apiError.code
      : expiredLocally || action.status === "expired"
        ? "ACTION_EXPIRED"
        : action.status === "cancelled" && (action.cancel_reason === "approval_stale" || action.cancel_reason === "superseded")
          ? "APPROVAL_STALE"
          : null;
  const busy = running !== null;

  const settle = async (updated: AgentAction | null) => {
    await invalidateAfterAction(queryClient);
    if (updated) onSettled?.(updated);
  };

  const runExecute = async () => {
    const result = await execute.mutateAsync(action.id);
    toast.show(outcomeToast(result));
    return result;
  };

  const approveAndStamp = async () => {
    setRunning("approve");
    decision.reset();
    execute.reset();
    let updated: AgentAction | null = null;
    try {
      await decision.mutateAsync({ action, decision: "approve" });
      setRunning("execute");
      updated = await runExecute();
    } catch {
      // The error shows in place; an approved action keeps a "Send" retry with the same key.
    } finally {
      setRunning(null);
      await settle(updated);
    }
  };

  const retryExecute = async () => {
    setRunning("execute");
    execute.reset();
    let updated: AgentAction | null = null;
    try {
      updated = await runExecute();
    } catch {
      // Shown in place.
    } finally {
      setRunning(null);
      await settle(updated);
    }
  };

  const confirmDecline = async () => {
    setRunning("decline");
    decision.reset();
    let updated: AgentAction | null = null;
    try {
      updated = await decision.mutateAsync({ action, decision: "decline", note });
      setDeclineOpen(false);
      setNote("");
      toast.show({ title: `${title} declined`, body: `Nothing was sent to ${review.recipient}.`, tone: "neutral" });
    } catch {
      // Shown in place.
    } finally {
      setRunning(null);
      await settle(updated);
    }
  };

  const reviewNewVersion = async () => {
    setLookingUp(true);
    decision.reset();
    execute.reset();
    const next = await findNewVersion(action);
    await invalidateAfterAction(queryClient);
    if (next) await queryClient.prefetchQuery({ queryKey: queryKeys.action(next), queryFn: () => fetchAction(next) });
    else toast.show({ title: "No new version could be prepared", body: "Ask the agent to prepare this action again.", tone: "danger" });
    setLookingUp(false);
    onNewVersion?.(next);
  };

  const bar = variant === "bar";

  return (
    <section aria-labelledby={headingId} className={cn("flex flex-col gap-4", className)}>
      {bar ? (
        <h3 id={headingId} className="sr-only">
          Decision on {title.toLowerCase()}
        </h3>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <h3 id={headingId} className="text-md font-bold">
              {title}
              {lineNo !== undefined && (
                <span className="font-regular text-muted">
                  {" "}
                  · line <Mono>{lineNumber(lineNo)}</Mono>
                </span>
              )}
            </h3>
            <StatusLine action={action} expiresMs={expiresMs} expiredLocally={expiredLocally} />
          </div>
          {action.rationale && (
            <p className="max-w-[70ch]">
              <span className="text-muted">Prepared by the VEYRA agent: </span>
              {action.rationale}
            </p>
          )}
          <ActionDetails action={action} animal={resolvedAnimal} evidenceOpen />
        </>
      )}

      <div className={cn("flex flex-col gap-3", !bar && "border-t-2 border-ink pt-4")}>
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <span>
            {lineNo !== undefined ? (
              <>
                Balance after line <Mono>{lineNumber(lineNo)}</Mono>
              </>
            ) : (
              "Sandbox balance after"
            )}
          </span>
          {review.balance_after_minor != null ? (
            <Money minor={review.balance_after_minor} currency={currency} className="text-md font-bold whitespace-nowrap" />
          ) : (
            <span className="text-muted">No payment in this step</span>
          )}
        </div>

        <DecisionArea
          action={action}
          title={title}
          isManager={isManager}
          blockingCode={blockingCode}
          error={blockingCode ? null : mutationError}
          busy={busy}
          running={running}
          lookingUp={lookingUp}
          declineOpen={declineOpen}
          note={note}
          noteId={noteId}
          onNote={setNote}
          onApprove={() => void approveAndStamp()}
          onExecute={() => void retryExecute()}
          onOpenDecline={() => {
            decision.reset();
            setDeclineOpen(true);
          }}
          onCancelDecline={() => setDeclineOpen(false)}
          onConfirmDecline={() => void confirmDecline()}
          onReviewNewVersion={() => void reviewNewVersion()}
        />
      </div>
    </section>
  );
}

function EvidenceManifest({ manifest, open }: { manifest: AgentAction["evidence_manifest"]; open: boolean }) {
  if (!manifest) return <p className="text-muted">No evidence manifest is attached.</p>;
  return (
    <details className="group" open={open}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 font-bold text-ink [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden="true" className="size-4 flex-none transition-transform group-open:rotate-90" strokeWidth={2.5} />
        <span>
          Evidence manifest <Mono>v{manifest.version}</Mono> · <Mono>{manifest.items.length}</Mono>{" "}
          {manifest.items.length === 1 ? "item" : "items"}
        </span>
      </summary>
      <ul className="flex flex-col border-t border-line">
        {manifest.items.map((item) => (
          <li
            key={`${item.type}-${item.ref}`}
            className="flex flex-wrap items-baseline justify-between gap-x-3 border-b border-line py-2 text-ink"
          >
            <span>{item.label}</span>
            <Mono className="text-sm text-muted">{item.ref}</Mono>
          </li>
        ))}
      </ul>
    </details>
  );
}

export interface ActionDetailsProps {
  action: AgentAction;
  /** Shown as a tag, name, and passport link; omit inside the animal's own passbook. */
  animal?: ActionReviewAnimal | null;
  evidenceOpen?: boolean;
  className?: string;
}

/** Exactly what will execute: recipient, animal, amount, terms, payload hash, and the evidence manifest. */
export function ActionDetails({ action, animal, evidenceOpen = false, className }: ActionDetailsProps) {
  const review = action.review;
  const currency = review.currency ?? "USD";
  const manifest = action.evidence_manifest;
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-5 gap-y-2">
        <Row label="Recipient">
          <span className="font-bold text-ink">{review.recipient}</span>
        </Row>
        {animal && (
          <Row label="Animal">
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <EarTag animalId={animal.id} state={animal.tagState} />
              <span className="font-bold">{animal.name}</span>
              <Link to={`/animals/${animal.id}`} className="figures text-sm">
                {animal.id}
              </Link>
            </span>
          </Row>
        )}
        <Row label="Amount">
          {review.amount_minor != null ? (
            <Money minor={review.amount_minor} currency={currency} className="font-bold text-ink" />
          ) : (
            <span className="text-muted">No amount</span>
          )}
        </Row>
        <Row label="Terms">
          {review.terms_version ? (
            <Mono className="text-ink">{review.terms_version}</Mono>
          ) : (
            <span className="text-muted">No terms attached</span>
          )}
        </Row>
        <Row label="Payload">
          <span className="text-ink">
            <Mono className="font-bold">{action.payload_hash.slice(0, 8)}</Mono>
            <span className="text-sm text-muted"> · version </span>
            <Mono className="text-sm">{action.version}</Mono>
          </span>
        </Row>
      </dl>
      <EvidenceManifest manifest={manifest} open={evidenceOpen} />
    </div>
  );
}

/** The awaiting passbook line's detail: what will execute, read from the action itself. */
export function ActionLineSummary({ actionId }: { actionId: string }) {
  const { data: action, isPending, error } = useAction(actionId);
  if (isPending) return <Skeleton lines={2} className="mt-2" />;
  if (error || !action) return <span>The action's details couldn't load.</span>;
  return (
    <div className="mt-1 flex flex-col">
      <p>
        To <span className="font-bold text-ink">{action.review.recipient}</span>
        {action.review.terms_version && (
          <>
            {" "}
            · terms <Mono className="text-ink">{action.review.terms_version}</Mono>
          </>
        )}{" "}
        · payload <Mono className="font-bold text-ink">{action.payload_hash.slice(0, 8)}</Mono> v<Mono>{action.version}</Mono>
      </p>
      <EvidenceManifest manifest={action.evidence_manifest} open={false} />
    </div>
  );
}

function StatusLine({ action, expiresMs, expiredLocally }: { action: AgentAction; expiresMs: number; expiredLocally: boolean }) {
  if (action.status === "pending_approval" && !expiredLocally) {
    return (
      <span className="text-sm text-await-ink">
        Expires in{" "}
        <time dateTime={action.expires_at} className="figures font-bold">
          {formatCountdown(expiresMs)}
        </time>
      </span>
    );
  }
  switch (action.status) {
    case "approved":
      return <StatusPill tone="awaiting" label="Approved, not sent" />;
    case "executing":
      return <StatusPill tone="awaiting" label="Sending" />;
    case "succeeded":
      return <StatusPill tone="ok" label="Posted" />;
    case "failed":
      return <StatusPill tone="danger" label="Failed" />;
    case "unknown":
      return <StatusPill tone="uncertain" label="Outcome unknown" />;
    case "declined":
      return <StatusPill tone="danger" label="Declined" />;
    case "cancelled":
      return <StatusPill tone="neutral" label="Cancelled" />;
    default:
      return <StatusPill tone="uncertain" label="Expired" />;
  }
}

interface DecisionAreaProps {
  action: AgentAction;
  title: string;
  isManager: boolean;
  blockingCode: string | null;
  error: unknown;
  busy: boolean;
  running: "approve" | "execute" | "decline" | null;
  lookingUp: boolean;
  declineOpen: boolean;
  note: string;
  noteId: string;
  onNote: (note: string) => void;
  onApprove: () => void;
  onExecute: () => void;
  onOpenDecline: () => void;
  onCancelDecline: () => void;
  onConfirmDecline: () => void;
  onReviewNewVersion: () => void;
}

function DecisionArea(props: DecisionAreaProps) {
  const { action, title, isManager, blockingCode, error, busy, running } = props;
  const recipient = action.review.recipient;

  if (blockingCode) {
    return (
      <div className="flex flex-col gap-3">
        <ErrorNotice code={blockingCode} />
        {(blockingCode === "APPROVAL_STALE" || blockingCode === "ACTION_EXPIRED") && (
          <div>
            <Button variant="primary" icon={RefreshCw} onClick={props.onReviewNewVersion} loading={props.lookingUp} loadingLabel="Preparing it…">
              {blockingCode === "APPROVAL_STALE" ? "Review the new version" : "Prepare it again"}
            </Button>
          </div>
        )}
      </div>
    );
  }

  if (action.status === "succeeded") {
    const ref = receiptRef(action.execution?.provider_receipt);
    return (
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Stamp kind="posted" at={action.execution?.completed_at ?? action.updated_at} by={providerName(action.execution?.provider_id)} press />
        </div>
        <p className="text-muted">
          {recipient} {ref ? <>confirmed with receipt <Mono className="text-ink">{ref}</Mono>.</> : "confirmed it."}
        </p>
      </div>
    );
  }
  if (action.status === "declined") {
    return (
      <div className="flex flex-col gap-2">
        <Stamp kind="declined" at={action.decided_at ?? action.updated_at} />
        <p className="text-muted">Nothing was sent to {recipient}.{action.decision_note ? ` Note: ${action.decision_note}` : ""}</p>
      </div>
    );
  }
  if (action.status === "failed") {
    const message = typeof action.execution?.error?.message === "string" ? action.execution.error.message : null;
    return (
      <div className="flex flex-col gap-2" role="alert">
        <Stamp kind="failed" at={action.execution?.completed_at ?? action.updated_at} />
        <p>{message ?? `${recipient} declined the request.`} Nothing was charged. Ask the agent to prepare it again.</p>
      </div>
    );
  }
  if (action.status === "cancelled") {
    return <p className="text-muted">This action was cancelled, so it will not run.</p>;
  }

  if (!isManager) {
    return (
      <p className="flex items-center gap-2 rounded-control bg-surface-2 p-4">
        <Lock aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
        Only a manager can approve. Switch role to Manager.
      </p>
    );
  }

  const errorNotice = error ? <ErrorNotice error={error} /> : null;

  if (action.status === "approved" || action.status === "executing" || action.status === "unknown") {
    const unknown = action.status === "unknown" || action.status === "executing";
    return (
      <div className="flex flex-col gap-3">
        <p>
          {unknown
            ? `No answer from ${recipient} yet. Checking again sends the same request key, so it can't run twice.`
            : `Approved. It has not reached ${recipient} yet.`}
        </p>
        {errorNotice}
        <Button
          variant="primary"
          size="decision"
          icon={unknown ? RotateCw : Send}
          onClick={props.onExecute}
          loading={running === "execute"}
          loadingLabel="Sending…"
          disabled={busy && running !== "execute"}
        >
          {unknown ? "Check again" : `Send to ${recipient}`}
        </Button>
      </div>
    );
  }

  if (props.declineOpen) {
    return (
      <div className="flex flex-col gap-3">
        <label htmlFor={props.noteId} className="font-bold">
          Decline this {title.toLowerCase()}?
        </label>
        <textarea
          id={props.noteId}
          value={props.note}
          onChange={(event) => props.onNote(event.target.value)}
          maxLength={2000}
          rows={2}
          placeholder="Reason for the record (optional)"
          className="min-h-11 w-full rounded-control border-2 border-line-strong bg-bg px-3 py-2 placeholder:text-muted focus:border-ink"
        />
        {errorNotice}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button variant="danger" size="decision" onClick={props.onConfirmDecline} loading={running === "decline"} loadingLabel="Declining…">
            Decline
          </Button>
          <Button variant="ghost" onClick={props.onCancelDecline} disabled={busy}>
            Keep it waiting
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {errorNotice}
      {/* Decline sits apart from Approve: 32px beside it, or 24px below it on a phone. */}
      <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:gap-0">
        <Button
          variant="primary"
          size="decision"
          icon={StampIcon}
          className="sm:flex-1"
          onClick={props.onApprove}
          loading={running === "approve" || running === "execute"}
          loadingLabel={running === "execute" ? `Sending to ${recipient}…` : "Approving…"}
          disabled={busy && running !== "approve" && running !== "execute"}
        >
          Approve and stamp
        </Button>
        <Button variant="danger" size="decision" className="flex-none sm:ml-8" onClick={props.onOpenDecline} disabled={busy}>
          Decline
        </Button>
      </div>
    </div>
  );
}
