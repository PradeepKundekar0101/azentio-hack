"use client";

import { useCallback, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Shared Recharts styling. Colours are CSS variables (validated in globals.css), so light
 * and dark mode each use their own steps. Marks are thin, grids recessive and solid.
 */
export const AXIS_PROPS = {
  stroke: "var(--chart-grid)",
  tick: { fill: "var(--chart-axis)", fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: "var(--chart-grid)" },
} as const;

/** Rounded data-end, square at the baseline (horizontal bars grow right). */
export const BAR_RADIUS_H: [number, number, number, number] = [0, 4, 4, 0];
/** Rounded data-end for vertical columns. */
export const BAR_RADIUS_V: [number, number, number, number] = [4, 4, 0, 0];

export const CURSOR_FILL = { fill: "var(--accent)", opacity: 0.6 };

export function ChartTooltip({
  active,
  payload,
  title,
  rows,
}: {
  active?: boolean;
  payload?: readonly { payload?: unknown }[];
  title: (datum: Record<string, unknown>) => React.ReactNode;
  rows: (datum: Record<string, unknown>) => { label: string; value: React.ReactNode; color?: string }[];
}) {
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload as Record<string, unknown>;
  return (
    <div className="max-w-64 min-w-44 rounded-lg bg-popover px-3 py-2 text-xs text-popover-foreground shadow-pop">
      <div className="mb-1 font-semibold">{title(datum)}</div>
      <dl className="space-y-0.5">
        {rows(datum).map((r) => (
          <div key={r.label} className="flex items-center justify-between gap-4">
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              {r.color && <span className="size-2 rounded-[2px]" style={{ background: r.color }} aria-hidden="true" />}
              {r.label}
            </dt>
            <dd className="num font-semibold">{r.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function LegendKey({ items, className }: { items: { label: string; color: string }[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground", className)}>
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px]" style={{ background: i.color }} aria-hidden="true" />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

export function ChartEmpty({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex h-full min-h-40 items-center justify-center px-6 text-center text-[13px] text-muted-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A screen-reader table with the same numbers as the chart beside it. */
export function ChartTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className="sr-only">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) =>
                j === 0 ? (
                  <th key={j} scope="row">
                    {cell}
                  </th>
                ) : (
                  <td key={j}>{cell}</td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Width of an element, kept current with a ResizeObserver. Null until first measured. */
export function useElementWidth<T extends HTMLElement>() {
  const [width, setWidth] = useState<number | null>(null);
  const ref = useCallback((node: T | null) => {
    if (!node) return;
    setWidth(node.getBoundingClientRect().width);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export interface BarListItem {
  key: string;
  label: string;
  /** Shown beside the label, e.g. the number of alerts. */
  detail?: string;
  value: number;
  display: string;
  color: string;
  onSelect?: () => void;
}

/**
 * Horizontal bars as plain HTML for narrow screens: the label sits above its bar, so long
 * names never squeeze the bars. Each row is a button when it can drill down.
 */
export function BarList({ items, label }: { items: BarListItem[]; label: string }) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul aria-label={label} className="space-y-1">
      {items.map((item) => {
        const body = (
          <>
            <span className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="min-w-0 truncate">
                {item.label}
                {item.detail && <span className="num ml-1.5 text-xs text-muted-foreground">{item.detail}</span>}
              </span>
              <span className="num shrink-0 font-medium">{item.display}</span>
            </span>
            <span aria-hidden="true" className="mt-1 block h-2 w-full overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full"
                style={{
                  width: `${Math.max(item.value > 0 ? 2 : 0, (item.value / max) * 100)}%`,
                  background: item.color,
                }}
              />
            </span>
          </>
        );
        return (
          <li key={item.key}>
            {item.onSelect ? (
              <button
                type="button"
                onClick={item.onSelect}
                className="block w-full rounded-md px-1.5 py-1.5 text-left outline-none hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring"
              >
                {body}
              </button>
            ) : (
              <div className="px-1.5 py-1.5">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
