"use client";

import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import { TableHead } from "@/components/ui/table";
import { type AlertSort, nextSort, type SortField, sortState } from "@/lib/alerts/filters";
import { cn } from "@/lib/utils";

/** A table header that sorts by its column; the current direction is announced via aria-sort. */
export function SortHeader({
  field,
  sort,
  onSort,
  children,
  align = "left",
  className,
}: {
  field: SortField;
  sort: AlertSort;
  onSort: (sort: AlertSort) => void;
  children: React.ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  const state = sortState(sort);
  const active = state.field === field;
  const Icon = !active ? ChevronsUpDown : state.desc ? ArrowDown : ArrowUp;
  return (
    <TableHead
      aria-sort={active ? (state.desc ? "descending" : "ascending") : "none"}
      className={cn(align === "right" && "text-right", className)}
    >
      <button
        type="button"
        onClick={() => onSort(nextSort(sort, field))}
        className={cn(
          "-mx-1.5 inline-flex h-7 items-center gap-1 rounded-md px-1.5 outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
          align === "right" && "flex-row-reverse",
          active && "text-foreground",
        )}
      >
        {children}
        <Icon className={cn("size-3.5", !active && "opacity-50")} aria-hidden="true" />
      </button>
    </TableHead>
  );
}
