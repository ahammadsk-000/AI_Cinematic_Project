// Mirrors the backend Pydantic schemas (apps/api/app/schemas). Keep in sync.

export type JobStatus =
  | "pending"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type StyleMode =
  | "cinematic_realistic"
  | "anime"
  | "cyberpunk"
  | "fantasy"
  | "portrait";

export type AspectRatio = "16:9" | "9:16" | "1:1";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Scene {
  id: string;
  index: number;
  summary: string;
  prompt: string;
  negative_prompt: string;
  camera: string;
  lighting: string;
  emotion: string;
  environment: string;
  motion: string;
  music_mood: string;
  narration: string;
  duration_sec: number;
}

export interface Asset {
  id: string;
  kind: "image" | "video" | "audio" | "subtitle" | "json";
  stage: string;
  scene_index: number | null;
  path: string;
}

export interface Job {
  id: string;
  title: string;
  script: string;
  style: StyleMode;
  aspect_ratio: AspectRatio;
  status: JobStatus;
  current_stage: string | null;
  progress_pct: number;
  error: string | null;
  result_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobDetail extends Job {
  scenes: Scene[];
  assets: Asset[];
}

export interface JobProgressEvent {
  job_id: string;
  status: JobStatus;
  stage: string | null;
  pct: number;
  message: string;
}

export interface CreateJobInput {
  script: string;
  title?: string;
  style?: StyleMode;
  aspect_ratio?: AspectRatio;
}

export interface SystemStatus {
  queue_depth: number | null;
  active_workers: number | null;
  worker_online: boolean;
  jobs_by_status: Record<string, number>;
}

// UI metadata for the pipeline stages (mirrors ai_engine PIPELINE_STAGES order).
export const PIPELINE_STAGES = [
  { key: "scene_generation", label: "Scenes" },
  { key: "prompt_enhancement", label: "Prompts" },
  { key: "image_generation", label: "Images" },
  { key: "character_lock", label: "Characters" },
  { key: "animation", label: "Animation" },
  { key: "voice", label: "Voice" },
  { key: "music", label: "Music" },
  { key: "compose", label: "Compose" },
] as const;
