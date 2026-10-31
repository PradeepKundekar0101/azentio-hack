"use client";

import { Check, Copy, Link2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Panel } from "@/components/page";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type Investigation, formatDelta, shortHash } from "@/lib/evidence/model";
import { EMPTY, formatDateTime, formatINR, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

function CopyHash({ hash }: { hash: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-md border bg-background/60 px-2 py-1 font-mono text-[11px] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => {
            void navigator.clipboard?.writeText(hash).then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          <Link2 className="size-3" aria-hidden="true" />
          {shortHash(hash, 12, 6)}
          {copied ? (
            <Check className="size-3 text-success" aria-hidden="true" />
          ) : (
            <Copy className="size-3" aria-hidden="true" />
          )}
          <span className="sr-only">{copied ? "Copied" : "Copy the full hash"}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-80 font-mono text-[11px] break-all">{hash}</TooltipContent>
    </Tooltip>
  );
}

/** The chain-of-custody seal: whether every recorded entry is unchanged, and the hash that proves it. */
export function IntegritySeal({ data }: { data: Investigation }) {
  const { integrity, investigation } = data;
  const ok = integrity.verified;
  const Icon = ok ? ShieldCheck : ShieldAlert;
  return (
    <Panel
      className={cn(
        "relative overflow-hidden",
        ok ? "border-success/25" : "border-destructive/40",
      )}
    >
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-y-0 left-0 w-1",
          ok ? "bg-success" : "bg-destructive",
        )}
      />
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4">
        <div className="flex min-w-0 items-center gap-3.5">
          <span
            className={cn(
              "grid size-11 shrink-0 place-items-center rounded-full",
              ok ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
            )}
          >
            <Icon className="size-5.5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold">
              {ok ? "Evidence chain verified" : "Evidence chain broken"}
            </p>
            <p className="text-[13px] text-muted-foreground">
              {ok ? (
                <>
                  <span className="num">{formatNumber(integrity.events)}</span>{" "}
                  {integrity.events === 1 ? "entry" : "entries"}, each sealed with SHA-256 and linked to the one
                  before. Nothing has changed since it was recorded.
                </>
              ) : (
                <>
                  Entry <span className="num">#{integrity.broken_at}</span>: {integrity.reason}. Treat this history
                  as tampered.
                </>
              )}
            </p>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px]">
          {investigation && (
            <span className="text-muted-foreground">
              Opened by <span className="font-medium text-foreground">{investigation.opened_by}</span>
              {" · "}
              <span className="num">{formatDateTime(investigation.opened_at)}</span>
            </span>
          )}
          {integrity.head_hash && <CopyHash hash={integrity.head_hash} />}
        </div>
      </div>
    </Panel>
  );
}

function Tile({
  label,
  value,
  hint,
  tone,
  emphasis = false,
}: {
  label: string;
  value: string;
  hint?: React.ReactNode;
  tone?: "good" | "bad";
  emphasis?: boolean;
}) {
  return (
    <div className={cn("min-w-0 px-4 py-3.5", emphasis && "bg-primary/[0.035] dark:bg-primary/[0.07]")}>
      <p className="text-[12px] font-medium text-muted-foreground">{label}</p>
      <p className="num mt-1 text-[22px] leading-7 font-semibold tracking-[-0.01em]">{value}</p>
      {hint && (
        <p
          className={cn(
            "num mt-0.5 text-[12px]",
            tone === "good" ? "text-success" : tone === "bad" ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {hint}
        </p>
      )}
    </div>
  );
}

/** Original vs current vs adjusted leakage, so every change from the first calculation is visible at a glance. */
export function SummaryTiles({ data }: { data: Investigation }) {
  const { summary } = data;
  const original = summary.original_calculated_leakage;
  const current = summary.current_calculated_leakage;
  const adjusted = summary.adjusted_calculated_leakage;
  const overrideDelta = formatDelta(current, adjusted);
  const runDelta = original == null ? null : formatDelta(original, current);
  return (
    <Panel className="grid grid-cols-2 divide-x divide-y lg:grid-cols-5 lg:divide-y-0 [&>*]:border-border">
      <Tile
        label="Original calculated leakage"
        value={original == null ? EMPTY : formatINR(original)}
        hint={original == null ? "Frozen when the investigation opens" : "Frozen at opening"}
      />
      <Tile
        label="Current calculation"
        value={formatINR(current)}
        hint={runDelta && runDelta !== formatINR("0") ? `${runDelta} since opening` : "Unchanged since opening"}
      />
      <Tile
        label="After analyst overrides"
        value={formatINR(adjusted)}
        emphasis
        tone={overrideDelta.startsWith("−") ? "good" : overrideDelta.startsWith("+") ? "bad" : undefined}
        hint={
          summary.overrides > 0
            ? `${overrideDelta} across ${summary.overrides} override${summary.overrides === 1 ? "" : "s"}`
            : "No overrides"
        }
      />
      <Tile label="Estimated, for review" value={formatINR(summary.estimated_leakage)} hint="Never deducted" />
      <Tile
        label="Findings decided"
        value={`${formatNumber(summary.decided)} / ${formatNumber(summary.findings)}`}
        hint={`${formatNumber(summary.counts.note ?? 0)} notes on record`}
      />
    </Panel>
  );
}
