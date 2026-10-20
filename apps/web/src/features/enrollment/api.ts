import { API_BASE, api } from "../../lib/api";
import { ApiError } from "../../lib/errors";
import { getToken } from "../../lib/role-store";
import type { components } from "../../lib/api-types";
import type { Decision, Enrollment, EnrollmentCreated, AnimalIn } from "./rules";

export type Job = components["schemas"]["JobOut"];

/** openapi-fetch returns `{ data }`; the error middleware has already thrown for non-2xx. */
function must<T>(data: T | undefined): T {
  if (data === undefined) throw new ApiError(500, "HTTP_ERROR", "The server sent an empty response.");
  return data;
}

export async function createEnrollment(sampleKey: string | null): Promise<EnrollmentCreated> {
  const { data } = await api.POST("/api/v1/enrollments", { body: { sample_key: sampleKey } });
  return must(data);
}

export async function getEnrollment(enrollmentId: string): Promise<Enrollment> {
  const { data } = await api.GET("/api/v1/enrollments/{enrollment_id}", {
    params: { path: { enrollment_id: enrollmentId } },
  });
  return must(data);
}

export async function processEnrollment(enrollmentId: string): Promise<string> {
  const { data } = await api.POST("/api/v1/enrollments/{enrollment_id}/process", {
    params: { path: { enrollment_id: enrollmentId } },
  });
  return must(data).job_id;
}

export async function getJob(jobId: string): Promise<Job> {
  const { data } = await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: jobId } } });
  return must(data);
}

export interface ConfirmInput {
  decision: Decision;
  animal?: AnimalIn | null;
  link_to?: string | null;
  override_note?: string | null;
  reject_reason?: string | null;
}

export async function confirmEnrollment(enrollmentId: string, body: ConfirmInput): Promise<Enrollment> {
  const { data } = await api.POST("/api/v1/enrollments/{enrollment_id}/confirm", {
    params: { path: { enrollment_id: enrollmentId } },
    body,
  });
  return must(data);
}

export async function retryEnrollment(enrollmentId: string): Promise<EnrollmentCreated> {
  const { data } = await api.POST("/api/v1/enrollments/{enrollment_id}/retry", {
    params: { path: { enrollment_id: enrollmentId } },
  });
  return must(data);
}

/**
 * PUT the video as multipart (`file`), with upload progress. fetch can't report request-body progress, so
 * this uses XMLHttpRequest. `onProgress` gets 0–1, or null while the total is unknown.
 */
export function uploadVideo(
  enrollmentId: string,
  file: Blob,
  filename: string,
  onProgress: (fraction: number | null) => void,
  signal?: AbortSignal,
): Promise<Enrollment> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `${API_BASE}/enrollments/${encodeURIComponent(enrollmentId)}/video`);
    xhr.setRequestHeader("Authorization", `Bearer ${getToken()}`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => onProgress(event.lengthComputable ? event.loaded / event.total : null);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as Enrollment);
      else reject(ApiError.fromEnvelope(xhr.status, xhr.response));
    };
    xhr.onerror = () => reject(ApiError.network());
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    const form = new FormData();
    form.append("file", file, filename);
    onProgress(0);
    xhr.send(form);
  });
}

export const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const id = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(id);
        reject(new DOMException("Cancelled", "AbortError"));
      },
      { once: true },
    );
  });

/** Poll the job until it settles, then return the enrollment as it now stands. */
export async function waitForProcessing(
  enrollmentId: string,
  jobId: string,
  onJob: (job: Job) => void,
  signal?: AbortSignal,
): Promise<Enrollment> {
  for (let attempt = 0; attempt < 600; attempt++) {
    const job = await getJob(jobId);
    onJob(job);
    if (job.status === "succeeded" || job.status === "failed") return getEnrollment(enrollmentId);
    await wait(attempt < 10 ? 600 : 1500, signal);
  }
  throw new ApiError(0, "NETWORK_ERROR", "Processing is taking longer than expected.");
}
