"use client";

import { useEffect } from "react";

import { useAuthStore } from "@/store/auth-store";

/** App-wide client providers. Re-validates the persisted token on first load. */
export function Providers({ children }: { children: React.ReactNode }) {
  const refreshUser = useAuthStore((s) => s.refreshUser);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  return <>{children}</>;
}
