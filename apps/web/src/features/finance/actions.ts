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
