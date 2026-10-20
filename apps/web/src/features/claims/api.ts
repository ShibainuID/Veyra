import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, request } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { queryKeys } from "../../lib/query-keys";
import { financeKeys, refreshFinance, type IncidentBody } from "../finance/api";

export type IdentityCheck = components["schemas"]["IdentityCheckOut"];
export type IdentityCheckResult = components["schemas"]["IdentityCheckResult"];
/** The demo outcomes (`IdentityCheckRequest.sample`); the request body schema is inlined in the contract. */
export type IdentitySample = "match" | "mismatch";
export type IdentityScanInput = { sample: IdentitySample } | { file: File };

/** Muzzle types the identity check accepts (photo or short video), as the server's allow-list. */
export const SCAN_ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime";

/**
 * Re-scan the claimed animal's muzzle: a photo or video upload (multipart), or a demo sample (JSON).
 * The server compares it with the enrolled muzzle and refreshes the claim's checklist.
 */
export function useIdentityCheck(claimId: string, animalId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: IdentityScanInput) => {
      const path = `/claims/${encodeURIComponent(claimId)}/identity-checks`;
      if ("file" in input) {
        const form = new FormData();
        form.append("file", input.file, input.file.name);
        return request<IdentityCheckResult>(path, { method: "POST", body: form });
      }
      return request<IdentityCheckResult>(path, { method: "POST", body: JSON.stringify({ sample: input.sample }) });
    },
    onSuccess: (result) => queryClient.setQueryData(financeKeys.claim(claimId), result.claim),
    onSettled: () =>
      Promise.all([
        refreshFinance(queryClient),
        queryClient.invalidateQueries({ queryKey: queryKeys.passport(animalId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.auditEvents }),
      ]),
  });
}

export function useClaims() {
  return useQuery({
    queryKey: financeKeys.claims,
    queryFn: async () => (await api.GET("/api/v1/claims")).data!.items,
  });
}

export function useClaim(claimId: string) {
  return useQuery({
    queryKey: financeKeys.claim(claimId),
    enabled: Boolean(claimId),
    queryFn: async () => (await api.GET("/api/v1/claims/{claim_id}", { params: { path: { claim_id: claimId } } })).data!,
  });
}

export function useIncident(incidentId: string | undefined) {
  return useQuery({
    queryKey: financeKeys.incident(incidentId ?? ""),
    enabled: Boolean(incidentId),
    queryFn: async () =>
      (await api.GET("/api/v1/incidents/{incident_id}", { params: { path: { incident_id: incidentId! } } })).data!,
  });
}

export function useCatalog() {
  return useQuery({
    queryKey: ["policies", "catalog"] as const,
    staleTime: Infinity,
    queryFn: async () => (await api.GET("/api/v1/policies/catalog")).data! as CatalogLike,
  });
}

export interface CatalogLike {
  products?: { product_id: string; name: string; covered_perils: string[] }[];
}

/** Records the incident, then drafts its claim. The incident stays recorded if the draft is refused. */
export function useRecordIncident() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: IncidentBody) => {
      const incident = (await api.POST("/api/v1/incidents", { body })).data!;
      try {
        const claim = (await api.POST("/api/v1/claims/drafts", { body: { incident_id: incident.id } })).data!;
        return { incident, claim, draftError: null as unknown };
      } catch (draftError) {
        return { incident, claim: null, draftError };
      }
    },
    onSettled: () => refreshFinance(queryClient),
  });
}

export function useAddFinding(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { summary: string; finding_type: "vet_assessment" | "vet_health_record" }) =>
      (await api.POST("/api/v1/incidents/{incident_id}/findings", { params: { path: { incident_id: incidentId } }, body }))
        .data!,
    onSettled: () => refreshFinance(queryClient),
  });
}

export function useConfirmDeclaration(claimId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      (await api.PATCH("/api/v1/claims/{claim_id}", { params: { path: { claim_id: claimId } }, body: { declaration_confirmed: true } }))
        .data!,
    onSuccess: (claim) => queryClient.setQueryData(financeKeys.claim(claimId), claim),
    onSettled: () => refreshFinance(queryClient),
  });
}
