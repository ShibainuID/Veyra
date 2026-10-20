/** Helpers for finding and linking agent actions from the screens that propose them. */
import { OPEN_STATUSES, type ActionType, type AgentAction } from "../actions";

export function isOpen(action: AgentAction): boolean {
  return OPEN_STATUSES.has(action.status);
}

/** The newest action of a type, optionally about one subject. */
export function latestAction(
  actions: readonly AgentAction[] | undefined,
  type: ActionType,
  subjectId?: string,
): AgentAction | undefined {
  return (actions ?? [])
    .filter((a) => a.action_type === type && (subjectId === undefined || a.subject_id === subjectId))
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
}

export function approvalsHref(actionId: string): string {
  return `/approvals?action=${encodeURIComponent(actionId)}`;
}

/**
 * Why the newest action of a kind is closed without having run, in one sentence for the screen
 * that prepares it again; null while it is open or once it succeeded.
 */
export function closedNote(action: AgentAction | undefined, what: string): string | null {
  if (!action) return null;
  switch (action.status) {
    case "failed":
      return `The last ${what} failed. Prepare it again.`;
    case "declined":
      return `The last ${what} was declined, so nothing was sent. Prepare it again if it is still needed.`;
    case "expired":
      return `The last ${what} expired before anyone decided, so nothing was sent. Prepare it again.`;
    case "cancelled":
      return action.cancel_reason === "approval_stale"
        ? `The records changed after the last ${what} was approved, so it was cancelled before it ran. Prepare it again from the current records.`
        : `The last ${what} was cancelled, so nothing was sent.`;
    default:
      return null;
  }
}
