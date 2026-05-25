"use client";

import { create } from "zustand";

import { api } from "@/lib/api";
import type { CreateJobInput, Job } from "@/types";

interface JobState {
  jobs: Job[];
  loading: boolean;
  error: string | null;
  fetchJobs: () => Promise<void>;
  createJob: (input: CreateJobInput) => Promise<Job>;
  cancelJob: (id: string) => Promise<void>;
  regenerateJob: (id: string) => Promise<void>;
  /** Patch a single job in the list from a live progress event. */
  patchJob: (id: string, patch: Partial<Job>) => void;
}

export const useJobStore = create<JobState>((set, get) => ({
  jobs: [],
  loading: false,
  error: null,

  async fetchJobs() {
    set({ loading: true, error: null });
    try {
      set({ jobs: await api.listJobs(), loading: false });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : "Failed to load jobs" });
    }
  },

  async createJob(input) {
    const job = await api.createJob(input);
    set({ jobs: [job, ...get().jobs] });
    return job;
  },

  async cancelJob(id) {
    const job = await api.cancelJob(id);
    get().patchJob(id, job);
  },

  async regenerateJob(id) {
    const job = await api.regenerateJob(id);
    get().patchJob(id, job);
  },

  patchJob(id, patch) {
    set({ jobs: get().jobs.map((j) => (j.id === id ? { ...j, ...patch } : j)) });
  },
}));
