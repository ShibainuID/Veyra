import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Send } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { Button, ButtonLink } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Provenance } from "../../components/Provenance";
import { StatusPill, type StatusTone } from "../../components/StatusPill";
import { request } from "../../lib/api";
import { tagStateFor } from "../../lib/animal";
import { cn } from "../../lib/cn";
import { toApiError } from "../../lib/errors";
import { Page } from "../../pages/Page";
import { agentKeys, isIntent, startConversation, useSendTurn, workingLabel, type AgentChoice, type AgentMessage, type Conversation, type Intent } from "./api";
import { CardView } from "./Cards";

const INTENT_TITLE: Record<Intent, string> = {
  find_insurance: "Find insurance",
  file_claim: "File a claim",
  track_claim: "Track a claim",
};

const COVERAGE_TONE: Record<string, StatusTone> = { active: "ok", pending: "awaiting", none: "danger" };

function ChoiceButton({ choice, onPick, disabled }: { choice: AgentChoice; onPick: (c: AgentChoice) => void; disabled: boolean }) {
  const variant = choice.style === "primary" ? "primary" : "secondary";
  if (choice.href) {
    return (
      <ButtonLink to={choice.href} variant={choice.style === "link" ? "ghost" : variant} className="min-h-12 justify-center">
        {choice.label}
      </ButtonLink>
    );
  }
  return (
    <Button variant={variant} className="min-h-12 justify-center" disabled={disabled} onClick={() => onPick(choice)}>
      {choice.label}
    </Button>
  );
}

function MessageView({
  message,
  latest,
  busy,
  onPick,
  onSettled,
}: {
  message: AgentMessage;
  latest: boolean;
  busy: boolean;
  onPick: (c: AgentChoice) => void;
  onSettled: () => void;
}) {
  if (message.role === "user") {
    return (
      <li className="flex justify-end">
        <p className="max-w-[85%] rounded-panel bg-ink px-4 py-3 text-bg">{message.text}</p>
      </li>
    );
  }
  const linkChoices = message.choices.filter((c) => c.href);
  const answerChoices = latest ? message.choices.filter((c) => !c.href) : [];
  return (
    <li className="flex flex-col gap-3">
      <div className="flex items-start gap-2">
        <Bot aria-hidden="true" className="mt-0.5 size-6 flex-none" strokeWidth={2.25} />
        <div className="flex min-w-0 flex-col gap-1">
          <p className="max-w-[68ch]">{message.text}</p>
          {message.source === "live" && <Provenance source="live" className="self-start" />}
        </div>
      </div>
      {message.cards.map((card, index) => (
        <CardView key={`${message.id}-${index}`} card={card} onSettled={onSettled} />
      ))}
      {(answerChoices.length > 0 || linkChoices.length > 0) && (
        <div className="grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
          {answerChoices.map((choice) => (
            <ChoiceButton key={`${choice.key}-${choice.value ?? ""}`} choice={choice} onPick={onPick} disabled={busy} />
          ))}
          {linkChoices.map((choice) => (
            <ChoiceButton key={`${choice.label}-${choice.href}`} choice={choice} onPick={onPick} disabled={busy} />
          ))}
        </div>
      )}
    </li>
  );
}

function Conversation({ conversation }: { conversation: Conversation }) {
  const send = useSendTurn(conversation.id);
  const [text, setText] = useState("");
  const [pendingKey, setPendingKey] = useState<string | undefined>();
  const inputId = useId();
  const endRef = useRef<HTMLDivElement>(null);
  const { data: current = conversation } = useQuery({
    queryKey: agentKeys.conversation(conversation.id),
    queryFn: () => request<Conversation>(`/agent/conversations/${encodeURIComponent(conversation.id)}`),
    initialData: conversation,
    staleTime: Infinity,
  });
  const messages = current.messages;
  const lastAgentSeq = [...messages].reverse().find((m) => m.role === "agent")?.seq;
  const busy = send.isPending;

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages.length, busy]);

  const pick = (choice: AgentChoice) => {
    setPendingKey(choice.key);
    send.mutate({ choice: { key: choice.key, value: choice.value } });
  };
  const onSettled = () => {
    setPendingKey("continue");
    send.mutate({ choice: { key: "continue", value: null } });
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setPendingKey(undefined);
    send.mutate({ text: value }, { onSuccess: () => setText("") });
  };
  const animal = current.animal;
  const summary = messages.flatMap((m) => m.cards).find((c) => c.type === "passport_summary");

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="flex min-w-0 flex-col gap-4">
        <ol className="flex flex-col gap-6" aria-live="polite">
          {messages.map((message) => (
            <MessageView
              key={message.id}
              message={message}
              latest={message.seq === lastAgentSeq}
              busy={busy}
              onPick={pick}
              onSettled={onSettled}
            />
          ))}
          {busy && (
            <li className="flex items-center gap-2 text-muted" role="status">
              <Bot aria-hidden="true" className="size-6 flex-none animate-pulse" strokeWidth={2.25} />
              {workingLabel(pendingKey, animal.name)}
            </li>
          )}
        </ol>
        {send.error && <ErrorNotice error={send.error} title={toApiError(send.error)?.message ?? "The agent couldn't reply"} />}
        <div ref={endRef} />
        <form onSubmit={onSubmit} className="sticky bottom-[calc(56px+env(safe-area-inset-bottom))] z-[1] flex gap-2 border-t-2 border-ink bg-bg py-3 lg:bottom-0">
          <label htmlFor={inputId} className="sr-only">
            Message the VEYRA agent
          </label>
          <input
            id={inputId}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={1000}
            placeholder="Type an answer, or choose above"
            className="min-h-12 min-w-0 flex-1 rounded-control border-2 border-line-strong bg-bg px-3 text-base placeholder:text-muted focus:border-ink"
          />
          <Button type="submit" variant="primary" icon={Send} disabled={busy || !text.trim()} className="min-h-12">
            Send
          </Button>
        </form>
      </div>
      <aside className="hidden lg:block">
        <div className="sticky top-24 flex flex-col gap-3">
          {summary && <CardView card={summary} onSettled={onSettled} />}
          <p className="text-sm text-muted">
            The agent prepares; a manager approves every application, payment, and claim. Insurer steps run in the sandbox
            with Sandbox Mutual, a fictional insurer.
          </p>
          <span className={cn("sr-only")}>{animal.id}</span>
        </div>
      </aside>
    </div>
  );
}

/** `/agent?animal=<id>&intent=<find_insurance|file_claim|track_claim>`: the guided agent conversation. */
export function AgentPage() {
  const [params] = useSearchParams();
  const animalId = params.get("animal");
  const intentParam = params.get("intent");
  const intent: Intent | null = isIntent(intentParam) ? intentParam : null;
  const queryClient = useQueryClient();
  const started = useQuery({
    queryKey: ["agent-start", animalId, intent],
    queryFn: async () => {
      const conversation = await startConversation(animalId as string, intent as Intent);
      queryClient.setQueryData(agentKeys.conversation(conversation.id), conversation);
      return conversation;
    },
    enabled: Boolean(animalId && intent),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });

  if (!animalId || !intent) {
    return (
      <Page>
        <EmptyState
          title="Start from an animal"
          action={<ButtonLink to="/herd" variant="primary">Open the herd</ButtonLink>}
        >
          Open an animal's coverage or claim and ask the VEYRA agent from there.
        </EmptyState>
      </Page>
    );
  }
  const conversation = started.data;
  return (
    <Page>
      <header className="mb-6 flex flex-wrap items-center gap-3 border-b-2 border-ink pb-4">
        {conversation ? (
          <>
            <EarTag animalId={conversation.animal.id} state={tagStateFor(conversation.animal.identity_status)} />
            <div className="flex min-w-0 flex-col">
              <h1 className="text-xl font-bold">
                {conversation.animal.name} · {INTENT_TITLE[intent]}
              </h1>
              <span className="text-sm text-muted">VEYRA agent · sandbox insurer</span>
            </div>
            <StatusPill
              tone={COVERAGE_TONE[conversation.animal.coverage_status] ?? "neutral"}
              label={conversation.animal.coverage_label}
              className="ml-auto"
            />
          </>
        ) : (
          <h1 className="text-xl font-bold">VEYRA agent · {INTENT_TITLE[intent]}</h1>
        )}
      </header>
      {started.isPending && (
        <LoadingRegion label="The agent is reading the passport">
          <p className="mb-3 text-muted">Reading the passport…</p>
          <Skeleton lines={4} />
        </LoadingRegion>
      )}
      {started.error && <ErrorNotice error={started.error} title="The agent couldn't start" onRetry={() => void started.refetch()} />}
      {conversation && <Conversation conversation={conversation} />}
    </Page>
  );
}
