"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Images, Loader2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { JobCard } from "@/components/job-card";
import { cn } from "@/lib/utils";
import { useJobStore } from "@/store/job-store";
import type { JobStatus } from "@/types";

const FILTERS: { key: JobStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "completed", label: "Completed" },
  { key: "running", label: "In progress" },
  { key: "failed", label: "Failed" },
];

export default function GalleryPage() {
  const { jobs, loading, fetchJobs } = useJobStore();
  const [filter, setFilter] = useState<JobStatus | "all">("all");

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  const filtered = jobs.filter((j) => {
    if (filter === "all") return true;
    if (filter === "running") return ["running", "queued", "pending"].includes(j.status);
    return j.status === filter;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold">
            <Images className="h-7 w-7 text-primary" /> Gallery
          </h1>
          <p className="text-muted-foreground">Every video you&apos;ve generated</p>
        </div>
        <Button variant="gradient" asChild>
          <Link href="/generate">
            <Plus className="h-4 w-4" /> New
          </Link>
        </Button>
      </div>

      <div className="flex gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={cn(
              "rounded-full px-3 py-1 text-sm transition-colors",
              filter === f.key ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-secondary/60",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex h-40 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <Card className="p-12 text-center text-muted-foreground">Nothing here yet.</Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
