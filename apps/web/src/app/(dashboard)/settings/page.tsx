"use client";

import { Settings as SettingsIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/auth-store";

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="space-y-6">
      <h1 className="flex items-center gap-2 text-3xl font-bold">
        <SettingsIcon className="h-7 w-7 text-primary" /> Settings
      </h1>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input defaultValue={user?.full_name ?? ""} disabled />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input defaultValue={user?.email ?? ""} disabled />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Generation defaults</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Default style, aspect ratio, and export presets will be configurable here. The GPU
            backend (ComfyUI / Ollama endpoints, VRAM budget) is configured via the worker&apos;s
            environment — see <code className="text-foreground">.env.example</code>.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
