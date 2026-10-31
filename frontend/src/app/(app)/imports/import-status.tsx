import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import type { DatasetCounts, IssueSeverity } from "@/lib/imports/model";
import { SEVERITY_LABELS } from "@/lib/imports/model";
import { cn } from "@/lib/utils";

export function BatchStatusBadge({ status }: { status: string }) {
  if (status === "completed") return <Badge variant="success">Completed</Badge>;
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  return <Badge variant="secondary">{status.charAt(0).toUpperCase() + status.slice(1)}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const label = SEVERITY_LABELS[severity as IssueSeverity] ?? severity;
  return <Badge variant={severity === "error" ? "destructive" : "warning"}>{label}</Badge>;
}

const SEGMENTS = [
  { key: "accepted", label: () => "accepted", className: "bg-success" },
  { key: "warnings", label: (n: number) => (n === 1 ? "warning" : "warnings"), className: "bg-warning" },
  { key: "rejected", label: () => "rejected", className: "bg-destructive" },
] as const;

/**
 * Received rows split into accepted, accepted with warnings and rejected. Decorative: the
 * same numbers are always written out next to it.
 */
export function ReconciliationBar({ counts, className }: { counts: DatasetCounts; className?: string }) {
  const total = counts.received;
  return (
    <div aria-hidden="true" className={cn("flex h-2 w-full gap-px overflow-hidden rounded-full bg-muted", className)}>
      {total > 0 &&
        SEGMENTS.map(({ key, className: color }) =>
          counts[key] > 0 ? (
            <div
              key={key}
              className={cn("h-full min-w-1", color)}
              style={{ flexGrow: counts[key], flexBasis: 0 }}
            />
          ) : null,
        )}
    </div>
  );
}

/** The three outcomes as a compact legend: "301 accepted · 4 warnings · 7 rejected". */
export function OutcomeLegend({ counts, className }: { counts: DatasetCounts; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap gap-x-3 gap-y-1 text-[13px] text-muted-foreground", className)}>
      {SEGMENTS.map(({ key, label, className: color }) => (
        <li key={key} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className={cn("size-2 rounded-full", counts[key] > 0 ? color : "bg-muted-foreground/30")} />
          <span>
            <span className={cn("num font-medium", counts[key] > 0 ? "text-foreground" : "text-muted-foreground")}>
              {formatNumber(counts[key])}
            </span>{" "}
            {label(counts[key])}
          </span>
        </li>
      ))}
    </ul>
  );
}
