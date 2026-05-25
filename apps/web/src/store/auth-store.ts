"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import { api, registerTokenGetter } from "@/lib/api";
import type { User } from "@/types";

interface AuthState {
  token: string | null;
  user: User | null;
  hydrated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      hydrated: false,

      async login(email, password) {
        const res = await api.login(email, password);
        set({ token: res.access_token, user: res.user });
      },

      async register(email, password, fullName) {
        const res = await api.register({ email, password, full_name: fullName });
        set({ token: res.access_token, user: res.user });
      },

      logout() {
        set({ token: null, user: null });
      },

      async refreshUser() {
        if (!get().token) return;
        try {
          set({ user: await api.me() });
        } catch {
          // token expired/invalid -> force logout
          set({ token: null, user: null });
        }
      },
    }),
    {
      name: "cineforge-auth",
      partialize: (s) => ({ token: s.token, user: s.user }),
      // Runs once localStorage has been read back in. Components gate redirects
      // on `hydrated` so there's no logged-out flash on first paint.
      onRehydrateStorage: () => () => {
        useAuthStore.setState({ hydrated: true });
      },
    },
  ),
);

// Expose the token to the API client without a circular import.
registerTokenGetter(() => useAuthStore.getState().token);
