"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth-store";
import type { JobProgressEvent, JobStatus } from "@/types";

const TERMINAL: JobStatus[] = ["completed", "failed", "cancelled"];

interface ProgressState {
  status: JobStatus | null;
  stage: string | null;
  pct: number;
  message: string;
  connected: boolean;
}

/**
 * Subscribe to a job's live progress stream.
 *
 * We deliberately do NOT use the browser EventSource API: it cannot send an
 * Authorization header, and our SSE endpoint is auth-protected. Instead we read
 * the text/event-stream with fetch + a ReadableStream reader and parse SSE frames
 * ourselves, which lets us attach the bearer token. Aborts cleanly on unmount.
 */
export function useJobProgress(jobId: string | null, enabled = true) {
  const token = useAuthStore((s) => s.token);
  const [state, setState] = useState<ProgressState>({
    status: null,
    stage: null,
    pct: 0,
    message: "",
    connected: false,
  });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!jobId || !enabled || !token) return;

    const controller = new AbortController();
    abortRef.current = controller;
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(api.streamUrl(jobId), {
          headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`);
        setState((s) => ({ ...s, connected: true }));

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by a blank line.
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const dataLine = frame
              .split("\n")
              .find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            try {
              const evt = JSON.parse(dataLine.slice(5).trim()) as
                | JobProgressEvent
                | { status: JobStatus; progress_pct?: number; current_stage?: string };
              const status = (evt as JobProgressEvent).status;
              const pct =
                (evt as JobProgressEvent).pct ??
                (evt as { progress_pct?: number }).progress_pct ??
                0;
              const stage =
                (evt as JobProgressEvent).stage ??
                (evt as { current_stage?: string }).current_stage ??
                null;
              setState((s) => ({
                ...s,
                status,
                pct,
                stage,
                message: (evt as JobProgressEvent).message ?? s.message,
              }));
              if (status && TERMINAL.includes(status)) {
                cancelled = true;
                break;
              }
            } catch {
              /* ignore malformed frame */
            }
          }
        }
      } catch {
        if (!cancelled) setState((s) => ({ ...s, connected: false }));
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jobId, enabled, token]);

  return state;
}
