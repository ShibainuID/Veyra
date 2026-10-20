import { useQuery } from "@tanstack/react-query";
import { request } from "../lib/api";

/** The herd summary from `GET /api/v1/animals` (backend task B3). */
export interface HerdSummary {
  animal_count: number;
  exposure_low_minor: number;
  exposure_high_minor: number;
  insured_minor: number;
  uncovered_count: number;
  open_alerts: number;
  pending_approvals: number;
  wallet_balance_minor: number;
  currency: string;
}

export interface AnimalsResponse {
  items: unknown[];
  summary: HerdSummary;
}

export const animalsQueryKey = ["animals"] as const;

/**
 * Wallet balance and approvals count for the shell. Shares the herd list query, so the herd page
 * and the shell read one request. Errors (including 404 before the endpoint exists) leave the
 * summary undefined, and the shell prints "—".
 */
export function useShellSummary() {
  return useQuery({
    queryKey: animalsQueryKey,
    queryFn: () => request<AnimalsResponse>("/animals"),
    select: (data) => data.summary,
    staleTime: 30_000,
  });
}
