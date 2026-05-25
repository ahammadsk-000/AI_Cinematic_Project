"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Film, Loader2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { JobCard } from "@/components/job-card";
import { WorkerStatus } from "@/components/worker-status";
import { useAuthStore } from "@/store/auth-store";
import { useJobStore } from "@/store/job-store";

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { jobs, loading, fetchJobs } = useJobStore();

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  const active = jobs.filter((j) => ["queued", "running", "pending"].includes(j.status)).length;
  const done = jobs.filter((j) => j.status === "completed").length;

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold">Welcome back{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}</h1>
          <p className="text-muted-foreground">Your cinematic studio</p>
        </div>
        <Button variant="gradient" asChild>
          <Link href="/generate">
            <Plus className="h-4 w-4" /> New video
          </Link>
        </Button>
      </div>

      <WorkerStatus />

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Total videos</p>
          <p className="mt-1 text-3xl font-bold">{jobs.length}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">In progress</p>
          <p className="mt-1 text-3xl font-bold text-accent">{active}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Completed</p>
          <p className="mt-1 text-3xl font-bold text-emerald-400">{done}</p>
        </Card>
      </div>

      <div>
        <h2 className="mb-4 text-lg font-semibold">Recent</h2>
        {loading ? (
          <div className="flex h-40 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : jobs.length === 0 ? (
          <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
            <Film className="h-10 w-10 text-muted-foreground/40" />
            <p className="text-muted-foreground">No videos yet. Create your first cinematic clip.</p>
            <Button variant="gradient" asChild>
              <Link href="/generate">
                <Plus className="h-4 w-4" /> Generate a video
              </Link>
            </Button>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {jobs.slice(0, 6).map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
