"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Download, Loader2, RefreshCw, XCircle } from "lucide-react";

import { PipelineProgress } from "@/components/pipeline-progress";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobProgress } from "@/hooks/use-job-progress";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { useJobStore } from "@/store/job-store";
import type { JobDetail } from "@/types";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const cancelJob = useJobStore((s) => s.cancelJob);
  const regenerateJob = useJobStore((s) => s.regenerateJob);

  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setJob(await api.getJob(id));
    setLoading(false);
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const live = useJobProgress(id, job ? !["completed", "failed", "cancelled"].includes(job.status) : false);

  // When the live stream reports terminal, reload the full detail (assets land then).
  useEffect(() => {
    if (live.status && ["completed", "failed"].includes(live.status)) void load();
  }, [live.status, load]);

  if (loading || !job) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const status = live.status ?? job.status;
  const inProgress = ["queued", "running", "pending"].includes(status);
  const stage = live.stage ?? job.current_stage;
  const pct = live.pct || job.progress_pct;

  async function handleCancel() {
    setBusy(true);
    try {
      await cancelJob(id);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function handleRegenerate() {
    setBusy(true);
    try {
      await regenerateJob(id);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link href="/gallery" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to gallery
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{job.title}</h1>
            <StatusBadge status={status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {job.style.replace(/_/g, " ")} · {job.aspect_ratio} · {formatDate(job.created_at)}
          </p>
        </div>
        <div className="flex gap-2">
          {inProgress && (
            <Button variant="outline" size="sm" onClick={handleCancel} disabled={busy}>
              <XCircle className="h-4 w-4" /> Cancel
            </Button>
          )}
          {["completed", "failed", "cancelled"].includes(status) && (
            <Button variant="outline" size="sm" onClick={handleRegenerate} disabled={busy}>
              <RefreshCw className="h-4 w-4" /> Regenerate
            </Button>
          )}
          {status === "completed" && job.result_path && (
            <Button variant="gradient" size="sm" asChild>
              <a href={job.result_path} download>
                <Download className="h-4 w-4" /> Download MP4
              </a>
            </Button>
          )}
        </div>
      </div>

      {/* result / progress */}
      <Card>
        <CardContent className="p-6">
          {status === "completed" && job.result_path ? (
            <video src={job.result_path} controls className="aspect-video w-full rounded-lg bg-black" />
          ) : status === "failed" ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-red-400">
              {job.error || "Generation failed."}
            </div>
          ) : (
            <PipelineProgress
              currentStage={stage}
              pct={pct}
              message={live.message || (live.connected ? "Working…" : "Waiting for a GPU worker to pick up the job…")}
            />
          )}
        </CardContent>
      </Card>

      {/* script */}
      <Card>
        <CardHeader>
          <CardTitle>Script</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{job.script}</p>
        </CardContent>
      </Card>

      {/* scenes */}
      {job.scenes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Scenes ({job.scenes.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {job.scenes.map((s) => (
              <div key={s.id} className="rounded-lg border border-border p-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-medium text-primary">Scene {s.index + 1}</span>
                  <span className="text-xs text-muted-foreground">{s.duration_sec.toFixed(1)}s</span>
                </div>
                <p className="text-sm">{s.summary}</p>
                {s.camera && <p className="mt-1 text-xs text-muted-foreground">🎥 {s.camera} · 💡 {s.lighting}</p>}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
