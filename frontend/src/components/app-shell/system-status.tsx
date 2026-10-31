"use client";

import { failedChecks, useHealth } from "@/lib/health";
import { cn } from "@/lib/utils";

type Tone = "pending" | "ok" | "warning" | "error";

const DOT: Record<Tone, string> = {
  pending: "bg-sidebar-foreground/30",
  ok: "bg-success",
  warning: "bg-warning",
  error: "bg-destructive",
};

function describe(health: ReturnType<typeof useHealth>): { tone: Tone; label: string } {
  if (health.isPending) return { tone: "pending", label: "Checking services" };
  if (health.isError) return { tone: "error", label: "Server unreachable" };
  const failed = failedChecks(health.data);
  if (failed.length === 0) return { tone: "ok", label: "All services running" };
  const names = failed.map((name) => name[0].toUpperCase() + name.slice(1)).join(" and ");
  return { tone: "warning", label: `${names} unavailable` };
}

/** Backend health from `GET /health`, shown at the foot of the sidebar. */
export function SystemStatus() {
  const { tone, label } = describe(useHealth());
  return (
    // Same insets as the nav links above, so the dot sits under their icons.
    <p role="status" className="flex h-5 items-center gap-2.5 px-2.5 text-xs text-sidebar-foreground/70">
      <span aria-hidden="true" className="flex size-4 shrink-0 items-center justify-center">
        <span className={cn("size-1.5 rounded-full", DOT[tone])} />
      </span>
      <span className="truncate">{label}</span>
    </p>
  );
}
