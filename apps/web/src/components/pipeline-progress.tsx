"use client";

import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { PIPELINE_STAGES } from "@/types";

interface Props {
  currentStage: string | null;
  pct: number;
  message?: string;
  isTerminal?: boolean;
}

/** Visual stepper for the 8-stage generation pipeline + an overall progress bar. */
export function PipelineProgress({ currentStage, pct, message, isTerminal }: Props) {
  const currentIdx = PIPELINE_STAGES.findIndex((s) => s.key === currentStage);

  return (
    <div className="space-y-4">
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
          transition={{ ease: "easeOut", duration: 0.4 }}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {PIPELINE_STAGES.map((stage, i) => {
          const done = isTerminal ? true : currentIdx > i;
          const active = !isTerminal && currentIdx === i;
          return (
            <div
              key={stage.key}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                done && "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
                active && "border-accent/40 bg-accent/10 text-accent",
                !done && !active && "border-border text-muted-foreground",
              )}
            >
              {done ? (
                <Check className="h-3 w-3" />
              ) : active ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <span className="h-3 w-3 rounded-full border border-current" />
              )}
              {stage.label}
            </div>
          );
        })}
      </div>

      {message && <p className="text-sm text-muted-foreground">{message}</p>}
    </div>
  );
}
