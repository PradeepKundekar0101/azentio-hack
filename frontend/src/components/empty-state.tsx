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
    <Panel className={cn("flex flex-col items-center px-6 py-12 text-center sm:py-16", className)}>
      <div className="flex size-10 items-center justify-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15 ring-inset">
        <Icon className="size-5" aria-hidden="true" />
      </div>
      <h2 className="mt-4 text-base leading-6 font-semibold">{title}</h2>
      <p className="mt-1 max-w-md text-sm text-pretty text-muted-foreground">{description}</p>
      {children}
      {actions && <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{actions}</div>}
    </Panel>
  );
}
