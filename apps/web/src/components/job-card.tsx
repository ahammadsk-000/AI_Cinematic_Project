"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Clapperboard, Film } from "lucide-react";

import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/lib/utils";
import type { Job } from "@/types";

export function JobCard({ job }: { job: Job }) {
  return (
    <motion.div whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 300 }}>
      <Link href={`/jobs/${job.id}`}>
        <Card className="group overflow-hidden">
          <div className="relative flex aspect-video items-center justify-center bg-gradient-to-br from-secondary to-background">
            <Film className="h-10 w-10 text-muted-foreground/40 transition-transform group-hover:scale-110" />
            <div className="absolute right-3 top-3">
              <StatusBadge status={job.status} />
            </div>
            {job.status === "running" && (
              <div className="absolute bottom-0 left-0 h-1 bg-accent" style={{ width: `${job.progress_pct}%` }} />
            )}
          </div>
          <div className="space-y-1 p-4">
            <div className="flex items-center gap-2">
              <Clapperboard className="h-4 w-4 shrink-0 text-primary" />
              <h3 className="truncate font-medium">{job.title}</h3>
            </div>
            <p className="line-clamp-2 text-sm text-muted-foreground">{job.script}</p>
            <p className="pt-1 text-xs text-muted-foreground/70">
              {job.style.replace(/_/g, " ")} · {job.aspect_ratio} · {formatDate(job.created_at)}
            </p>
          </div>
        </Card>
      </Link>
    </motion.div>
  );
}
