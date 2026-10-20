/**
 * Query keys shared across features. Invalidation works on prefixes: invalidating `["animals"]`
 * refreshes the shell summary and every filtered herd list; `["actions"]` refreshes every action.
 */
export interface HerdFilters {
  coverage?: "none" | "active" | "pending";
  alerts?: "open";
  q?: string;
}

export interface ActionListParams {
  status?: "draft" | "pending_approval" | "approved" | "declined" | "expired" | "cancelled" | "executing" | "succeeded" | "failed" | "unknown";
  animal_id?: string;
}

export interface AuditFilters {
  animal_id?: string;
  subject_type?: string;
}

export const queryKeys = {
  /** The unfiltered herd list; the shell summary reads this exact key. */
  animals: ["animals"] as const,
  herd: (filters: HerdFilters) => ["animals", "herd", filters] as const,
  passports: ["passport"] as const,
  passport: (animalId: string) => ["passport", animalId] as const,
  observations: (animalId: string) => ["observations", animalId] as const,
  actions: ["actions"] as const,
  action: (actionId: string) => ["actions", "detail", actionId] as const,
  actionList: (params: ActionListParams) => ["actions", "list", params] as const,
  wallet: ["wallet"] as const,
  auditEvents: ["audit-events"] as const,
  audit: (filters: AuditFilters) => ["audit-events", filters] as const,
};
