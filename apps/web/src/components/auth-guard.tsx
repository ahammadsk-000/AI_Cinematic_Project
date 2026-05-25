"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { useAuthStore } from "@/store/auth-store";

/** Wrap protected pages. We gate on a client-side `mounted` flag rather than the
 *  persist rehydration callback: zustand's localStorage hydration is synchronous,
 *  so by the time this effect runs on the client the token is already available.
 *  This avoids the SSR/first-paint flash AND the "stuck spinner" that happens if
 *  the rehydration callback never fires. */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !token) router.replace("/login");
  }, [mounted, token, router]);

  if (!mounted || !token) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  return <>{children}</>;
}
