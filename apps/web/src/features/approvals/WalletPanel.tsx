import { ArrowDownLeft, ArrowUpRight, FlaskConical, Lock, LockOpen, type LucideIcon } from "lucide-react";
import { useId } from "react";
import { Link } from "react-router";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { EarTag } from "../../components/EarTag";
import { Money, Timestamp } from "../../components/figures";
import { tagStateFor } from "../../lib/animal";
import { cn } from "../../lib/cn";
import { formatMoney } from "../../lib/format";
import { useWallet } from "../actions";
import { useAnimals, type WalletEntry } from "../finance/api";

/** "Release hold · Premium payment" under a "Release" label reads "Premium payment", not the word twice. */
function withoutLeadingWord(description: string, word: string): string {
  const [head, ...rest] = description.split(" · ");
  return rest.length && head!.toLowerCase().startsWith(word.toLowerCase()) ? rest.join(" · ") : description;
}

const ANIMAL_ID = /^animal-[\w-]+$/;

/** Splits a ledger description into the animal it names (shown as the row's tag) and the remaining words. */
function splitAnimal(text: string): { animalId: string | null; rest: string } {
  const parts = text.split(" · ");
  const animalId = parts.find((part) => ANIMAL_ID.test(part)) ?? null;
  return { animalId, rest: parts.filter((part) => part !== animalId).join(" · ") };
}

const ENTRY: Record<WalletEntry["entry_type"], { icon: LucideIcon; word: string; sign: 1 | -1 | 0 }> = {
  credit: { icon: ArrowDownLeft, word: "Credit", sign: 1 },
  debit: { icon: ArrowUpRight, word: "Debit", sign: -1 },
  hold: { icon: Lock, word: "Hold", sign: 0 },
  release: { icon: LockOpen, word: "Release", sign: 0 },
};

/** The agent's sandbox wallet: what it holds, what is reserved, and every movement, newest first. */
export function WalletPanel({ className }: { className?: string }) {
  const headingId = useId();
  const wallet = useWallet();
  const animals = useAnimals();
  const identity = new Map((animals.data?.items ?? []).map((a) => [a.id, a.identity_status]));
  return (
    <section aria-labelledby={headingId} className={cn("flex flex-col gap-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={headingId} className="text-lg font-bold">
          Agent wallet
        </h2>
        <span className="inline-flex h-8 items-center gap-1.5 rounded-pill border-2 border-dashed border-muted px-3 text-sm font-bold text-muted">
          <FlaskConical aria-hidden="true" className="size-4" strokeWidth={2.25} />
          Sandbox · no real funds
        </span>
      </div>
      {wallet.isPending ? (
        <LoadingRegion label="Loading the sandbox wallet">
          <Skeleton height="88px" />
          <Skeleton lines={4} className="mt-4" />
        </LoadingRegion>
      ) : wallet.error || !wallet.data ? (
        <ErrorNotice error={wallet.error} title="The wallet couldn't load" onRetry={() => void wallet.refetch()} retrying={wallet.isRefetching} />
      ) : (
        <>
          <dl className="grid grid-cols-2 border-y-2 border-ink">
            <div className="col-span-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-line py-3">
              <dt className="text-sm text-muted">Balance</dt>
              <dd className="text-lg font-bold">
                <Money minor={wallet.data.balance_minor} currency={wallet.data.currency} />
              </dd>
            </div>
            <div className="flex flex-col gap-1 py-3 pr-3">
              <dt className="text-sm text-muted">Available</dt>
              <dd className="font-bold">
                <Money minor={wallet.data.available_minor} currency={wallet.data.currency} />
              </dd>
            </div>
            <div className="flex flex-col gap-1 border-l border-line py-3 pl-3">
              <dt className="text-sm text-muted">Held</dt>
              <dd className={cn("font-bold", wallet.data.held_minor > 0 && "text-await-ink")}>
                <Money minor={wallet.data.held_minor} currency={wallet.data.currency} />
              </dd>
            </div>
          </dl>
          <p className="text-sm text-muted">A premium is held when its payment starts, then debited when the provider confirms, or released if it fails.</p>
          <h3 className="text-md font-bold">Ledger</h3>
          {wallet.data.entries.length === 0 ? (
            <p className="text-muted">No movements yet.</p>
          ) : (
            <ol className="flex flex-col border-t border-line">
              {[...wallet.data.entries]
                .sort((a, b) => b.created_at.localeCompare(a.created_at))
                .map((entry) => {
                  const kind = ENTRY[entry.entry_type];
                  const Icon = kind.icon;
                  const { animalId, rest } = splitAnimal(withoutLeadingWord(entry.description, kind.word));
                  const fullText = [kind.word, rest, animalId].filter(Boolean).join(" · ");
                  const figure =
                    kind.sign === 0
                      ? formatMoney(entry.amount_minor, entry.currency)
                      : formatMoney(kind.sign * entry.amount_minor, entry.currency, { signed: true });
                  return (
                    // The tag sits in its own leading column so the description keeps to one line.
                    <li key={entry.id} className="grid grid-cols-[auto_3.25rem_minmax(0,1fr)_auto] items-start gap-x-3 border-b border-line py-3">
                      <Icon aria-hidden="true" className="mt-0.5 size-5 text-muted" strokeWidth={2.25} />
                      <span className="flex min-h-6 items-start">
                        {animalId && <EarTag animalId={animalId} state={tagStateFor(identity.get(animalId) ?? "confirmed")} />}
                      </span>
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <span className="truncate" title={fullText}>
                          <span className="font-bold">{kind.word}</span>
                          {rest && <> · {rest}</>}
                        </span>
                        <span className="text-sm text-muted">
                          <Timestamp value={entry.created_at} mode="absolute" />
                          {entry.action_id && (
                            <>
                              {" "}
                              ·{" "}
                              <Link to={`/approvals?action=${encodeURIComponent(entry.action_id)}`} className="figures">
                                {entry.action_id}
                              </Link>
                            </>
                          )}
                        </span>
                      </div>
                      <span
                        className={cn(
                          "figures text-right font-bold whitespace-nowrap",
                          kind.sign === 1 && "text-ok",
                          kind.sign === 0 && "font-regular text-muted",
                        )}
                      >
                        {figure}
                      </span>
                    </li>
                  );
                })}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
