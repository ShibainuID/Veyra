import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, request } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { queryKeys } from "../../lib/query-keys";
import { financeKeys } from "../finance/api";

export type AnimalDocument = components["schemas"]["AnimalDocumentOut"];
export type DocumentKind = AnimalDocument["kind"];

/** The server's allow-list (domain/documents.py): PDF, JPEG, PNG, up to 10 MB. */
export const DOCUMENT_ACCEPT = "application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png";
export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;

export const DOCUMENT_KINDS: readonly { value: DocumentKind; label: string }[] = [
  { value: "ownership", label: "Ownership" },
  { value: "purchase_receipt", label: "Purchase receipt" },
  { value: "vet_record", label: "Vet record" },
  { value: "other", label: "Other" },
];

export function documentKindLabel(kind: string): string {
  return DOCUMENT_KINDS.find((k) => k.value === kind)?.label ?? kind;
}

/** "2.4 KB", "1.3 MB": file sizes for the documents list. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const documentKeys = { list: (animalId: string) => ["documents", animalId] as const };

export function useDocuments(animalId: string) {
  return useQuery({
    queryKey: documentKeys.list(animalId),
    queryFn: async () => {
      const result = await api.GET("/api/v1/animals/{animal_id}/documents", { params: { path: { animal_id: animalId } } });
      return result.data!.items;
    },
  });
}

export interface DocumentUpload {
  file: File;
  kind: DocumentKind;
  title?: string;
}

/**
 * Keep a document on the passport. An ownership document becomes the animal's ownership reference, so the
 * passport, the herd, and the insurance eligibility all refresh afterwards.
 */
export function useUploadDocument(animalId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, kind, title }: DocumentUpload) => {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("kind", kind);
      if (title?.trim()) form.append("title", title.trim());
      return request<AnimalDocument>(`/animals/${encodeURIComponent(animalId)}/documents`, { method: "POST", body: form });
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: documentKeys.list(animalId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.passport(animalId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.animals }),
        queryClient.invalidateQueries({ queryKey: queryKeys.auditEvents }),
        queryClient.invalidateQueries({ queryKey: financeKeys.recommendations(animalId) }),
      ]),
  });
}
