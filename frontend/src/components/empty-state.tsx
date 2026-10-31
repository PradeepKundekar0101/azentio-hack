import type { LucideIcon } from "lucide-react";

import { Panel } from "@/components/page";
import { cn } from "@/lib/utils";

/** A page or panel with nothing to show yet: what will appear here and the next step. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  children,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <Panel className={cn("relative isolate flex flex-col items-center overflow-hidden px-6 py-12 text-center sm:py-16", className)}>
      <div aria-hidden="true" className="surface-grid absolute inset-0 -z-10" />
      <div className="flex size-12 items-center justify-center rounded-xl bg-[linear-gradient(to_bottom,color-mix(in_oklch,var(--primary)_14%,var(--card)),color-mix(in_oklch,var(--primary)_6%,var(--card)))] text-primary shadow-raised ring-1 ring-primary/15 ring-inset">
        <Icon className="size-5" aria-hidden="true" strokeWidth={1.75} />
      </div>
      <h2 className="mt-5 text-[17px] leading-6 font-semibold tracking-[-0.01em]">{title}</h2>
      <p className="mt-1 max-w-md text-sm text-pretty text-muted-foreground">{description}</p>
      {children}
      {actions && <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{actions}</div>}
    </Panel>
  );
}
