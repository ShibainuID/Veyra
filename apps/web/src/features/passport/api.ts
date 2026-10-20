import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { queryKeys, type HerdFilters } from "../../lib/query-keys";

type Schemas = components["schemas"];
export type Passport = Schemas["Passport"];
export type PassportAnimal = Schemas["PassportAnimal"];
export type PassbookLineOut = Schemas["PassbookLine"];
export type HerdItem = Schemas["AnimalListItem"];
export type AnimalObservations = Schemas["AnimalObservations"];
export type ValuationRequest = Schemas["ValuationRequest"];
export type ValuationOut = Schemas["ValuationOut"];
export type EstimateOut = Schemas["EstimateOut"];

function must<T>(result: { data?: T }): T {
  if (result.data === undefined) throw new Error("The response had no body.");
  return result.data;
}

export function usePassport(animalId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.passport(animalId ?? ""),
    queryFn: async () =>
      must(await api.GET("/api/v1/animals/{animal_id}/passport", { params: { path: { animal_id: animalId! } } })),
    enabled: Boolean(animalId),
  });
}

export function useObservations(animalId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.observations(animalId ?? ""),
    queryFn: async () =>
      must(await api.GET("/api/v1/animals/{animal_id}/observations", { params: { path: { animal_id: animalId! } } })),
    enabled: Boolean(animalId),
  });
}

export function useHerd(filters: HerdFilters) {
  return useQuery({
    queryKey: queryKeys.herd(filters),
    queryFn: async () => must(await api.GET("/api/v1/animals", { params: { query: filters } })),
    placeholderData: (previous) => previous,
  });
}

export function useConfirmValuation(animalId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ValuationRequest) =>
      must(await api.POST("/api/v1/animals/{animal_id}/valuations", { params: { path: { animal_id: animalId } }, body })),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.passport(animalId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.animals }),
        queryClient.invalidateQueries({ queryKey: queryKeys.auditEvents }),
      ]);
    },
  });
}
