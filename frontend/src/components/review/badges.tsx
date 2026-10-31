import { Badge } from "@/components/ui/badge";
import {
  alertStatusLabel,
  AMOUNT_TYPE_DEFINITIONS,
  type AmountType,
  amountTypeLabel,
  severityLabel,
} from "@/lib/alerts/model";
import { outcomeLabel } from "@/lib/claims/model";
import { formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

const SEVERITY_CLASSES: Record<string, string> = {
  critical: "bg-destructive text-primary-foreground dark:text-background",
  high: "bg-destructive/10 text-destructive dark:bg-destructive/20",
  medium: "bg-warning/10 text-warning dark:bg-warning/15",
  low: "bg-secondary text-secondary-foreground",
  review: "bg-primary/8 text-primary dark:bg-primary/15",
};

export function SeverityBadge({ severity, className }: { severity: string; className?: string }) {
  return (
    <Badge variant="secondary" className={cn(SEVERITY_CLASSES[severity], className)}>
      {severityLabel(severity)}
    </Badge>
  );
}

/**
 * Amount types are told apart by the outline (solid, dashed, dotted) and a symbol as well as
 * colour, so they read the same for everyone and never look like a severity.
 */
const AMOUNT_TYPE_STYLES: Record<string, { symbol: string; className: string }> = {
  calculated: { symbol: "=", className: "border-primary/40 text-primary" },
  estimated: { symbol: "≈", className: "border-dashed border-foreground/35 text-foreground" },
  suspected: { symbol: "?", className: "border-dotted border-muted-foreground/60 text-muted-foreground" },
};

export function AmountTypeBadge({ type, className }: { type: string; className?: string }) {
  const style = AMOUNT_TYPE_STYLES[type] ?? AMOUNT_TYPE_STYLES.suspected;
  return (
    <Badge
      variant="outline"
      title={AMOUNT_TYPE_DEFINITIONS[type as AmountType]}
      className={cn("gap-1 bg-transparent px-1.5 font-medium", style.className, className)}
    >
      <span aria-hidden="true" className="num w-2 text-center leading-none">
        {style.symbol}
      </span>
      {amountTypeLabel(type)}
    </Badge>
  );
}

/** An alert amount with its type badge. Suspected alerts have no amount. */
export function AlertAmount({
  amount,
  type,
  className,
  size = "sm",
  badgeFirst = false,
}: {
  amount: string | null;
  type: string;
  className?: string;
  size?: "sm" | "lg";
  /** Badge before the amount, so right-aligned amounts line up in a column. */
  badgeFirst?: boolean;
}) {
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-x-2 gap-y-1", className)}>
      {badgeFirst && <AmountTypeBadge type={type} />}
      <span
        className={cn(
          "num font-semibold",
          size === "lg" && "text-2xl leading-8 tracking-[-0.01em]",
          amount === null && "font-normal text-muted-foreground",
        )}
      >
        {amount === null ? "No amount" : formatINR(amount)}
      </span>
      {!badgeFirst && <AmountTypeBadge type={type} />}
    </span>
  );
}

const STATUS_CLASSES: Record<string, string> = {
  open: "border-border bg-card text-foreground",
  evidence_requested: "bg-warning/10 text-warning dark:bg-warning/15",
  escalated: "bg-destructive/10 text-destructive dark:bg-destructive/20",
  reviewed: "bg-success/10 text-success dark:bg-success/15",
  dismissed: "bg-secondary text-muted-foreground",
};

export function AlertStatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(STATUS_CLASSES[status], status !== "open" && "border-transparent", className)}
    >
      {status === "open" && <span aria-hidden="true" className="size-1.5 rounded-full bg-primary" />}
      {alertStatusLabel(status)}
    </Badge>
  );
}

const OUTCOME_CLASSES: Record<string, string> = {
  fail: "bg-destructive/10 text-destructive dark:bg-destructive/20",
  adjusted: "bg-primary/8 text-primary dark:bg-primary/15",
  pass: "bg-success/10 text-success dark:bg-success/15",
  not_applicable: "bg-transparent text-muted-foreground border-border",
};

export function OutcomeBadge({ outcome, className }: { outcome: string; className?: string }) {
  return (
    <Badge variant="outline" className={cn("border-transparent", OUTCOME_CLASSES[outcome], className)}>
      {outcomeLabel(outcome)}
    </Badge>
  );
}
