"use client";

import { useEffect, useState } from "react";
import { Cpu, Layers } from "lucide-react";

import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SystemStatus } from "@/types";

/** Live GPU-worker + queue indicator (the "queue dashboard" surface). Polls the
 *  /system/status endpoint; degrades quietly if the broker is unreachable. */
export function WorkerStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const s = await api.systemStatus();
        if (active) setStatus(s);
      } catch {
        /* ignore — keep last known */
      }
    };
    void tick();
    const id = setInterval(tick, 10_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const online = status?.worker_online ?? false;

  return (
    <Card className="flex items-center justify-between p-4">
      <div className="flex items-center gap-3">
        <Cpu className="h-5 w-5 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium">GPU worker</p>
          <p className="text-xs text-muted-foreground">
            {online
              ? `${status?.active_workers ?? 1} online`
              : "Offline — start a Colab/Kaggle session to render"}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Layers className="h-4 w-4" />
          {status?.queue_depth ?? 0} queued
        </div>
        <span className="relative flex h-2.5 w-2.5">
          {online && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          )}
          <span
            className={cn(
              "relative inline-flex h-2.5 w-2.5 rounded-full",
              online ? "bg-emerald-400" : "bg-muted-foreground/40",
            )}
          />
        </span>
      </div>
    </Card>
  );
}
