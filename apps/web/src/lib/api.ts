// Typed API client for the Cineforge backend.
//
// Requests go to "/api/..." which Next rewrites to the backend (see next.config),
// so the browser stays same-origin. The JWT is read from the auth store's token
// getter, injected here, so components never touch headers directly.

import type {
  CreateJobInput,
  Job,
  JobDetail,
  SystemStatus,
  Token,
  User,
} from "@/types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// Set by the auth store on init so the client can attach the bearer token
// without importing the store (avoids a circular dependency).
let tokenGetter: () => string | null = () => null;
export function registerTokenGetter(fn: () => string | null) {
  tokenGetter = fn;
}

const BASE = "/api/v1";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = tokenGetter();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // --- auth ---
  register(data: { email: string; password: string; full_name?: string }) {
    return request<Token>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  login(email: string, password: string) {
    // OAuth2 password flow expects form-encoded `username`/`password`
    const form = new URLSearchParams({ username: email, password });
    return request<Token>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
  },
  me() {
    return request<User>("/auth/me");
  },

  // --- jobs ---
  createJob(data: CreateJobInput) {
    return request<Job>("/jobs", { method: "POST", body: JSON.stringify(data) });
  },
  listJobs() {
    return request<Job[]>("/jobs");
  },
  getJob(id: string) {
    return request<JobDetail>(`/jobs/${id}`);
  },
  cancelJob(id: string) {
    return request<Job>(`/jobs/${id}/cancel`, { method: "POST" });
  },
  regenerateJob(id: string) {
    return request<Job>(`/jobs/${id}/regenerate`, { method: "POST" });
  },

  // SSE endpoint URL (consumed by useJobProgress via EventSource).
  streamUrl(id: string) {
    return `${BASE}/jobs/${id}/stream`;
  },

  // --- system / queue ---
  systemStatus() {
    return request<SystemStatus>("/system/status");
  },
};
