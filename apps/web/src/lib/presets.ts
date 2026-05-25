import type { AspectRatio, JobStatus, StyleMode } from "@/types";

export const STYLE_OPTIONS: { value: StyleMode; label: string; blurb: string }[] = [
  { value: "cinematic_realistic", label: "Cinematic Realistic", blurb: "Film-grade lighting, shallow depth of field" },
  { value: "anime", label: "Anime", blurb: "Stylized cel-shaded, expressive" },
  { value: "cyberpunk", label: "Cyberpunk", blurb: "Neon, rain, dystopian futurism" },
  { value: "fantasy", label: "Fantasy", blurb: "Epic, painterly, magical" },
  { value: "portrait", label: "Portrait", blurb: "Character-focused, consistent faces" },
];

export const ASPECT_OPTIONS: { value: AspectRatio; label: string; hint: string }[] = [
  { value: "16:9", label: "16:9 — Cinematic / YouTube", hint: "Landscape" },
  { value: "9:16", label: "9:16 — Reels / Shorts", hint: "Vertical" },
  { value: "1:1", label: "1:1 — Feed post", hint: "Square" },
];

// Cinematic preset prompts the user can drop into the generator (advanced feature).
export const CINEMATIC_PRESETS: { name: string; script: string }[] = [
  {
    name: "Rainy Cyberpunk",
    script:
      "A young boy walks through a rainy cyberpunk city at night. Neon signs reflect in puddles. The mood is lonely and tense while cinematic synth music plays.",
  },
  {
    name: "Epic Fantasy Journey",
    script:
      "A lone knight crosses a misty mountain pass at dawn, then descends into an ancient glowing forest. Triumphant orchestral score.",
  },
  {
    name: "Noir Detective",
    script:
      "A detective enters a dim, smoky office. Venetian-blind shadows stripe the wall. Slow jazz, suspenseful and moody.",
  },
];

export const STATUS_META: Record<
  JobStatus,
  { label: string; variant: "default" | "accent" | "success" | "warning" | "destructive" | "muted" }
> = {
  pending: { label: "Pending", variant: "muted" },
  queued: { label: "Queued", variant: "warning" },
  running: { label: "Running", variant: "accent" },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "muted" },
};
