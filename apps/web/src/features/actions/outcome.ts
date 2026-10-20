import type { ToastInput } from "../../components/Toast";
import type { AgentAction } from "./types";

const RECEIPT_FIELDS = ["payment_ref", "application_ref", "notification_ref", "claim_ref", "confirmation_ref"] as const;

const RECEIVED: Record<string, string> = {
  PREMIUM_PAYMENT: "received the payment",
  POLICY_APPLICATION: "accepted the application",
  INSURER_NOTIFICATION: "received the notification",
  CLAIM_SUBMISSION: "received the claim",
};

/** The provider's reference from a receipt ("SBX-PAY-…"), if it carries one. */
export function receiptRef(receipt: Record<string, unknown> | null | undefined): string | null {
  if (!receipt) return null;
  for (const field of RECEIPT_FIELDS) {
    const value = receipt[field];
    if (typeof value === "string" && value) return value;
  }
  return null;
}

/** The toast after an execution: the provider's result in plain words, with its receipt. */
export function outcomeToast(action: AgentAction): ToastInput {
  const recipient = action.review.recipient || "The provider";
  const execution = action.execution;
  if (action.status === "succeeded") {
    const ref = receiptRef(execution?.provider_receipt);
    const words = RECEIVED[action.action_type] ?? "received the request";
    return {
      title: ref ? `${recipient} ${words} · receipt ${ref}` : `${recipient} ${words}`,
      body: "Stamped and posted to the passbook.",
      tone: "ok",
    };
  }
  if (action.status === "unknown" || action.status === "executing") {
    return {
      title: `No answer from ${recipient} yet`,
      body: "Check again: the same request is reconciled with the provider, never sent twice.",
      tone: "neutral",
      duration: 0,
    };
  }
  const message = typeof execution?.error?.message === "string" ? execution.error.message : null;
  return {
    title: `${recipient} did not accept it`,
    body: message ?? "The provider declined the request. Nothing was charged.",
    tone: "danger",
    duration: 0,
  };
}
