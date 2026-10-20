import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { financeKeys, refreshFinance, type IncidentBody } from "../finance/api";

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
