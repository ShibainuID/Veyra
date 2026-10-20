import { MessageSquareText, Send } from "lucide-react";
import { useId, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { Button } from "../../components/Button";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { ApiError } from "../../lib/errors";
import { ASK_PLACEHOLDER, SUGGESTED_QUERIES, type AssistantAnswer } from "./answer";
import { AnswerCard } from "./AnswerCard";

/* ---------- Session history, shared by the drawer and /ask ---------- */

export interface Exchange {
  id: number;
  question: string;
  status: "pending" | "done" | "error";
  answer?: AssistantAnswer;
  error?: unknown;
}

let history: readonly Exchange[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function update(next: readonly Exchange[]) {
  history = next;
  listeners.forEach((l) => l());
}

function useHistory(): readonly Exchange[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => history,
    () => history,
  );
}

export async function ask(question: string): Promise<void> {
  const id = nextId++;
  update([{ id, question, status: "pending" }, ...history]);
  const settle = (patch: Partial<Exchange>) => update(history.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  try {
    const { data } = await api.POST("/api/v1/assistant/query", { body: { text: question } });
    if (!data) throw new ApiError(500, "HTTP_ERROR", "Empty answer.");
    settle({ status: "done", answer: data });
  } catch (error) {
    settle({ status: "error", error });
  }
}

/** Test hook. */
export function resetAskHistory() {
  history = [];
  nextId = 1;
  listeners.forEach((l) => l());
}

/* ---------- Panel ---------- */

export function AskPanel({ autoFocus = false, className }: { autoFocus?: boolean; className?: string }) {
  const items = useHistory();
  const [text, setText] = useState("");
  const inputId = useId();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const busy = items.some((e) => e.status === "pending");

  function submit(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setText("");
    void ask(q);
    inputRef.current?.focus();
  }

  return (
    <div className={cn("flex flex-col gap-6", className)}>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          submit(text);
        }}
        className="flex flex-col gap-3"
      >
        <label htmlFor={inputId} className="sr-only">
          Your question
        </label>
        <div className="flex items-stretch gap-2">
          <textarea
            id={inputId}
            ref={inputRef}
            rows={2}
            value={text}
            autoFocus={autoFocus}
            placeholder={ASK_PLACEHOLDER}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(text);
              }
            }}
            className="min-h-12 min-w-0 flex-1 resize-none rounded-control border-2 border-ink bg-bg px-3 py-2.5 text-base placeholder:text-muted"
          />
          <Button type="submit" variant="primary" icon={Send} disabled={!text.trim()} loading={busy} loadingLabel="Asking…" className="self-stretch">
            Ask
          </Button>
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-sm font-bold text-muted">Try</p>
          <ul className="flex flex-wrap gap-2">
            {SUGGESTED_QUERIES.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => submit(q)}
                  className="min-h-11 rounded-control border-2 border-line-strong bg-bg px-3 py-1.5 text-left text-sm font-bold hover:border-ink hover:bg-surface disabled:cursor-not-allowed disabled:text-muted"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </form>

      {items.length === 0 ? (
        <div className="flex items-start gap-3 text-muted">
          <MessageSquareText aria-hidden="true" className="mt-0.5 size-5 flex-none" strokeWidth={2.25} />
          <p>
            Answers come from the farm's own records: passports, camera observations, cover, and alerts. A location is
            always the last observation on record, never a live position.
          </p>
        </div>
      ) : (
        <ol className="flex flex-col gap-8" aria-live="polite">
          {items.map((exchange) => (
            <li key={exchange.id} className="flex flex-col gap-3 border-t-2 border-ink pt-4">
              <p className="font-bold">
                <span className="sr-only">You asked: </span>
                {exchange.question}
              </p>
              {exchange.status === "pending" && (
                <LoadingRegion label="Looking through the records">
                  <Skeleton lines={3} />
                </LoadingRegion>
              )}
              {exchange.status === "error" && (
                <ErrorNotice
                  error={exchange.error}
                  title="No answer this time"
                  onRetry={() => {
                    update(history.filter((e) => e.id !== exchange.id));
                    void ask(exchange.question);
                  }}
                />
              )}
              {exchange.status === "done" && exchange.answer && <AnswerCard answer={exchange.answer} />}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
