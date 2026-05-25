"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Sparkles, Wand2 } from "lucide-react";

import { PipelineProgress } from "@/components/pipeline-progress";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useJobProgress } from "@/hooks/use-job-progress";
import { ASPECT_OPTIONS, CINEMATIC_PRESETS, STYLE_OPTIONS } from "@/lib/presets";
import { useJobStore } from "@/store/job-store";
import type { AspectRatio, StyleMode } from "@/types";

export default function GeneratePage() {
  const router = useRouter();
  const createJob = useJobStore((s) => s.createJob);

  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [style, setStyle] = useState<StyleMode>("cinematic_realistic");
  const [aspect, setAspect] = useState<AspectRatio>("16:9");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  // Live progress once a job exists.
  const progress = useJobProgress(jobId, jobId !== null);
  const isTerminal = ["completed", "failed", "cancelled"].includes(progress.status ?? "");

  async function onGenerate() {
    setError(null);
    if (script.trim().length < 4) {
      setError("Please write a longer script.");
      return;
    }
    setSubmitting(true);
    try {
      const job = await createJob({
        script,
        title: title || "Untitled",
        style,
        aspect_ratio: aspect,
      });
      setJobId(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start generation");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold">
          <Sparkles className="h-7 w-7 text-primary" /> Generate
        </h1>
        <p className="text-muted-foreground">Describe your scene — Cineforge handles the rest.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* editor */}
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Script</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="My cinematic short" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="script">Story / prompt</Label>
                <Textarea
                  id="script"
                  value={script}
                  onChange={(e) => setScript(e.target.value)}
                  className="min-h-[180px]"
                  placeholder="A young boy walks through a rainy cyberpunk city while cinematic music plays..."
                />
              </div>

              <div>
                <Label className="mb-2 block">Cinematic presets</Label>
                <div className="flex flex-wrap gap-2">
                  {CINEMATIC_PRESETS.map((p) => (
                    <Button key={p.name} variant="outline" size="sm" onClick={() => setScript(p.script)}>
                      <Wand2 className="h-3.5 w-3.5" /> {p.name}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {jobId && (
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>Generation progress</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => router.push(`/jobs/${jobId}`)}>
                  Open job →
                </Button>
              </CardHeader>
              <CardContent>
                <PipelineProgress
                  currentStage={progress.stage}
                  pct={progress.pct}
                  message={progress.message || (progress.connected ? "Working…" : "Connecting to worker…")}
                  isTerminal={isTerminal && progress.status === "completed"}
                />
              </CardContent>
            </Card>
          )}
        </div>

        {/* settings */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Style</Label>
                <Select value={style} onValueChange={(v) => setStyle(v as StyleMode)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STYLE_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {STYLE_OPTIONS.find((o) => o.value === style)?.blurb}
                </p>
              </div>

              <div className="space-y-2">
                <Label>Aspect ratio</Label>
                <Select value={aspect} onValueChange={(v) => setAspect(v as AspectRatio)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ASPECT_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {error && <p className="text-sm text-red-400">{error}</p>}

              <Button
                variant="gradient"
                className="w-full"
                onClick={onGenerate}
                disabled={submitting || (jobId !== null && !isTerminal)}
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {jobId && !isTerminal ? "Generating…" : "Generate video"}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
