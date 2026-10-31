"use client";

import { ArrowRight, History, PencilLine, Quote, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Panel, PanelHeader } from "@/components/page";
import { AmountTypeBadge, SeverityBadge } from "@/components/review/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { describePattern } from "@/lib/alerts/model";
import {
  type EvidenceFinding,
  type Investigation,
  decisionLabel,
  decisionTone,
  isOverridden,
} from "@/lib/evidence/model";
import { formatDateTime, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

import { OverrideDialog } from "./override-dialog";

const TONE_CLASSES = {
  good: "bg-success/10 text-success",
  bad: "bg-destructive/10 text-destructive",
  warn: "bg-warning/10 text-warning",
  neutral: "bg-secondary text-secondary-foreground",
} as const;

function Amount({ label, value, strike, strong }: { label: string; value: string | null; strike?: boolean; strong?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
      <p
        className={cn(
          "num mt-0.5 text-[15px] font-semibold",
          strike && "font-normal text-muted-foreground line-through decoration-muted-foreground/60",
          strong && "text-primary",
        )}
      >
        {value === null ? "No amount" : formatINR(value)}
      </p>
    </div>
  );
}

function FindingCard({ claimId, finding }: { claimId: string; finding: EvidenceFinding }) {
  const [editing, setEditing] = useState(false);
  const rec = finding.recommendation;
  const original = finding.original_recommendation;
  const overridden = isOverridden(finding);
  const pattern = describePattern(rec.rule_or_pattern);
  const decision = finding.decision;

  return (
    <li className="group relative px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">{finding.category_label}</h3>
            <SeverityBadge severity={finding.severity} />
            <AmountTypeBadge type={rec.amount_type} />
          </div>
          <p className="mt-1 max-w-[70ch] text-[13px] text-pretty text-muted-foreground">{finding.explanation}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className={cn("font-medium", TONE_CLASSES[decisionTone(decision?.status)])}>
            {decisionLabel(decision?.status)}
          </Badge>
          <Button asChild variant="ghost" size="sm" className="text-muted-foreground">
            <Link href={`/alerts/${finding.alert_id}`}>Alert</Link>
          </Button>
        </div>
      </div>

      <div className="mt-3 rounded-lg border bg-background/50 p-3">
        <p className="flex items-center gap-1.5 text-[13px] font-medium">
          <Sparkles className="size-3.5 text-primary" aria-hidden="true" />
          {rec.action}
        </p>
        <div className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:items-end">
          <Amount label="Original" value={rec.original_amount} />
          <ArrowRight className="hidden size-4 text-muted-foreground sm:block" aria-hidden="true" />
          {overridden ? (
            <div className="flex gap-4">
              <Amount label="Recommended" value={rec.correction} strike />
              <Amount label="Applied" value={finding.effective_correction ?? null} strong />
            </div>
          ) : (
            <Amount label="Correction" value={rec.correction} strong />
          )}
          <ArrowRight className="hidden size-4 text-muted-foreground sm:block" aria-hidden="true" />
          <Amount label="Pay" value={finding.effective_corrected_amount ?? null} />
        </div>
        {rec.calculation && (
          <p className="num mt-2.5 rounded-md bg-muted/60 px-2.5 py-1.5 font-mono text-[12px]">{rec.calculation}</p>
        )}
        <p className="mt-2 text-[12px] text-muted-foreground">
          {pattern.code && <span className="num font-medium text-foreground">{pattern.code}</span>} {pattern.name}
          {rec.policy_rule_id && (
            <>
              {" · "}
              <span className="num">{rec.policy_rule_id}</span>
            </>
          )}
          {" · "}
          {rec.basis}
        </p>
      </div>

      {finding.changed_since_opened && original && (
        <p className="mt-2.5 flex items-center gap-1.5 text-[12px] text-warning">
          <History className="size-3.5" aria-hidden="true" />
          A later run changed this recommendation. It was {formatINR(original.correction)} when the investigation
          opened.
        </p>
      )}

      {overridden && finding.override && (
        <figure className="mt-3 border-l-2 border-primary/40 pl-3">
          <blockquote className="flex gap-1.5 text-[13px] text-pretty">
            <Quote className="mt-0.5 size-3.5 shrink-0 text-primary/60" aria-hidden="true" />
            {finding.override.reason}
          </blockquote>
          <figcaption className="mt-1 text-[12px] text-muted-foreground">
            {finding.override.actor} · <span className="num">{formatDateTime(finding.override.at)}</span> · entry{" "}
            <span className="num">#{finding.override.seq}</span>
          </figcaption>
        </figure>
      )}

      {decision?.note && (
        <p className="mt-2.5 text-[12px] text-muted-foreground">
          <span className="font-medium text-foreground">{decision.actor}</span>: {decision.note}
        </p>
      )}

      <div className="mt-3 flex justify-end">
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
          <PencilLine data-icon="inline-start" aria-hidden="true" />
          {overridden ? "Change override" : "Override correction"}
        </Button>
      </div>
      <OverrideDialog claimId={claimId} finding={finding} open={editing} onOpenChange={setEditing} />
    </li>
  );
}

export function FindingsPanel({ data }: { data: Investigation }) {
  return (
    <Panel>
      <PanelHeader
        title="Findings and recommended corrections"
        description="What the rules engine recommends for each finding, and what analysts applied instead."
      />
      {data.findings.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-muted-foreground">
          No findings on this claim in the latest run.
        </p>
      ) : (
        <ul className="divide-y">
          {data.findings.map((finding) => (
            <FindingCard key={finding.key} claimId={data.claim.claim_id} finding={finding} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

type Step = { step_code: string; explanation: string; amount_before: string; reduction: string; amount_after: string };

export function OriginalCalculation({ data }: { data: Investigation }) {
  const original = data.original;
  if (!original || original.payable_steps.length === 0) return null;
  const steps = original.payable_steps as Step[];
  return (
    <Panel>
      <PanelHeader
        title="Original calculation"
        description={
          <>
            Frozen when the investigation opened
            {original.run_id != null && (
              <>
                {" "}
                (run <span className="num">#{original.run_id}</span>)
              </>
            )}
            . Later runs never change this copy.
          </>
        }
      />
      <ol className="px-4 py-3">
        {steps.map((step, index) => {
          const reduced = Number(step.reduction) > 0;
          return (
            <li key={`${step.step_code}-${index}`} className="grid grid-cols-[auto_1fr_auto] gap-x-3 py-2">
              <span
                className={cn(
                  "num mt-0.5 grid size-5 place-items-center rounded-full text-[11px] font-semibold",
                  reduced ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
                )}
              >
                {index + 1}
              </span>
              <div className="min-w-0">
                <p className="text-[13px] font-medium">{describePattern(step.step_code).name || step.step_code}</p>
                <p className="text-[12px] text-pretty text-muted-foreground">{step.explanation}</p>
              </div>
              <div className="text-right">
                <p className="num text-[13px] font-semibold">{formatINR(step.amount_after)}</p>
                {reduced && <p className="num text-[12px] text-destructive">−{formatINR(step.reduction)}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
