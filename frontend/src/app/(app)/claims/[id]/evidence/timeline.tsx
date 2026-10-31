"use client";

import {
  Calculator,
  ChevronDown,
  Download,
  FolderOpen,
  Gavel,
  Link2,
  LoaderCircle,
  type LucideIcon,
  MessageSquareText,
  PencilLine,
  RefreshCw,
} from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { Panel, PanelHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getErrorMessage } from "@/lib/api/errors";
import { useAddNote } from "@/lib/evidence/hooks";
import {
  EVIDENCE_FILTERS,
  type EvidenceEvent,
  type EvidenceFilter,
  type Investigation,
  KIND_LABELS,
  decisionLabel,
  matchesFilter,
  relativeTime,
} from "@/lib/evidence/model";
import { formatDateTime, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

const KIND_STYLE: Record<EvidenceEvent["kind"], { icon: LucideIcon; className: string }> = {
  opened: { icon: FolderOpen, className: "bg-primary text-primary-foreground" },
  recalculated: { icon: RefreshCw, className: "bg-chart-2/15 text-chart-2" },
  decision: { icon: Gavel, className: "bg-success/12 text-success" },
  override: { icon: PencilLine, className: "bg-warning/12 text-warning" },
  note: { icon: MessageSquareText, className: "bg-secondary text-secondary-foreground" },
  exported: { icon: Download, className: "bg-muted text-muted-foreground" },
};

type Payload = Record<string, unknown>;
const str = (value: unknown) => (value == null ? null : String(value));

function Detail({ event, findings }: { event: EvidenceEvent; findings: Map<string, string> }) {
  const p = event.payload as Payload;
  const finding = event.finding_key ? findings.get(event.finding_key) : undefined;
  switch (event.kind) {
    case "opened": {
      const totals = (p.totals ?? {}) as Payload;
      return (
        <dl className="grid grid-cols-3 gap-2 text-[12px]">
          <div>
            <dt className="text-muted-foreground">Findings</dt>
            <dd className="num font-medium">{str(totals.findings) ?? "0"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Calculated</dt>
            <dd className="num font-medium">{formatINR(str(totals.calculated_leakage))}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Payable</dt>
            <dd className="num font-medium">{formatINR(str(totals.payable))}</dd>
          </div>
        </dl>
      );
    }
    case "override": {
      const original = (p.original_recommendation ?? {}) as Payload;
      return (
        <div className="space-y-1.5 text-[12px]">
          {finding && <p className="text-muted-foreground">{finding}</p>}
          <p className="num flex flex-wrap items-center gap-1.5">
            <span className="text-muted-foreground line-through">{formatINR(str(p.previous_correction))}</span>
            <span aria-hidden="true">→</span>
            <span className="font-semibold">{formatINR(str(p.new_correction))}</span>
            <span className="text-muted-foreground">
              (system recommended {formatINR(str(original.correction))})
            </span>
          </p>
          <p className="rounded-md bg-muted/60 px-2 py-1.5 text-pretty">“{str(p.reason)}”</p>
        </div>
      );
    }
    case "decision":
      return (
        <div className="space-y-1 text-[12px]">
          <p className="text-muted-foreground">
            {finding ?? "Finding"}: {decisionLabel(str(p.previous))} → <span className="font-medium text-foreground">{decisionLabel(str(p.status))}</span>
          </p>
          {p.note ? <p className="rounded-md bg-muted/60 px-2 py-1.5 text-pretty">“{str(p.note)}”</p> : null}
        </div>
      );
    case "note":
      return (
        <div className="space-y-1 text-[12px]">
          {finding && <p className="text-muted-foreground">On {finding}</p>}
          <p className="text-[13px] whitespace-pre-wrap text-pretty">{str(p.text)}</p>
        </div>
      );
    case "recalculated": {
      const changes = (p.changes ?? {}) as { added?: Payload[]; removed?: Payload[]; changed?: Payload[]; payable?: Payload | null };
      return (
        <ul className="space-y-0.5 text-[12px] text-muted-foreground">
          {(changes.added ?? []).map((f) => (
            <li key={`a-${str(f.key)}`}>
              <span className="font-medium text-destructive">New</span> {str(f.category)} {formatINR(str(f.amount))}
            </li>
          ))}
          {(changes.removed ?? []).map((f) => (
            <li key={`r-${str(f.key)}`}>
              <span className="font-medium text-success">Resolved</span> {str(f.category)}
            </li>
          ))}
          {(changes.changed ?? []).map((c) => (
            <li key={`c-${str(c.key)}`} className="num">
              <span className="font-medium text-foreground">Changed</span> {str(c.key)?.split("|")[0]}:{" "}
              {formatINR(str((c.before as Payload).amount))} → {formatINR(str((c.after as Payload).amount))}
            </li>
          ))}
          {changes.payable && (
            <li className="num">
              Payable {formatINR(str(changes.payable.before))} → {formatINR(str(changes.payable.after))}
            </li>
          )}
        </ul>
      );
    }
    case "exported":
      return (
        <p className="text-[12px] text-muted-foreground">
          {String(p.format ?? "").toUpperCase()} report covering <span className="num">{str(p.events_covered)}</span>{" "}
          entries.
        </p>
      );
    default:
      return null;
  }
}

function TimelineItem({ event, last, findings }: { event: EvidenceEvent; last: boolean; findings: Map<string, string> }) {
  const [showHash, setShowHash] = useState(false);
  const style = KIND_STYLE[event.kind];
  const Icon = style.icon;
  return (
    <li className="relative grid grid-cols-[auto_1fr] gap-x-3 pb-5 last:pb-1">
      {!last && <span aria-hidden="true" className="absolute top-8 bottom-0 left-[15px] w-px bg-border" />}
      <span className={cn("relative z-10 grid size-8 place-items-center rounded-full ring-4 ring-card", style.className)}>
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 pt-0.5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <p className="text-[13px] font-semibold">{KIND_LABELS[event.kind]}</p>
          <time
            className="num shrink-0 text-[12px] text-muted-foreground"
            dateTime={event.at}
            title={formatDateTime(event.at)}
          >
            {relativeTime(event.at)}
          </time>
        </div>
        {event.kind !== "note" && <p className="mt-0.5 text-[13px] text-pretty">{event.summary}</p>}
        <div className="mt-2">
          <Detail event={event} findings={findings} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="grid size-4.5 place-items-center rounded-full bg-muted text-[10px] font-semibold text-foreground uppercase">
              {event.actor.slice(0, 1)}
            </span>
            <span className="font-medium text-foreground">{event.actor}</span>
            {event.actor_role && <span>· {event.actor_role.replaceAll("_", " ")}</span>}
          </span>
          <span aria-hidden="true">·</span>
          <span className="num">{formatDateTime(event.at)}</span>
          <span aria-hidden="true">·</span>
          <button
            type="button"
            onClick={() => setShowHash((v) => !v)}
            className="inline-flex items-center gap-1 rounded-sm font-mono text-[11px] outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            aria-expanded={showHash}
          >
            <Link2 className="size-3" aria-hidden="true" />#{event.seq} {event.hash.slice(0, 8)}
            <ChevronDown className={cn("size-3 transition-transform", showHash && "rotate-180")} aria-hidden="true" />
          </button>
        </div>
        {showHash && (
          <dl className="mt-1.5 grid gap-0.5 rounded-md border bg-muted/40 p-2 font-mono text-[10.5px] break-all text-muted-foreground">
            <div>
              <dt className="inline text-foreground">hash </dt>
              <dd className="inline">{event.hash}</dd>
            </div>
            <div>
              <dt className="inline text-foreground">prev </dt>
              <dd className="inline">{event.prev_hash ?? "none (first entry)"}</dd>
            </div>
          </dl>
        )}
      </div>
    </li>
  );
}

function NoteComposer({ data }: { data: Investigation }) {
  const [text, setText] = useState("");
  const [alertId, setAlertId] = useState<string>("");
  const addNote = useAddNote(data.claim.claim_id);
  const textId = useId();
  const findingId = useId();

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    addNote.mutate(
      { text: trimmed, alertId: alertId ? Number(alertId) : null },
      {
        onSuccess: () => {
          setText("");
          toast.success("Note added to the evidence history");
        },
        onError: (error) => toast.error(getErrorMessage(error)),
      },
    );
  };

  return (
    <form
      className="grid gap-2 border-b px-4 py-3"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Label htmlFor={textId} className="sr-only">
        Add a note
      </Label>
      <Textarea
        id={textId}
        value={text}
        rows={2}
        maxLength={2000}
        className="min-h-16 resize-y text-[13px]"
        placeholder="Add a note: what you checked, who you spoke to, what is pending…"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
        }}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        {data.findings.length > 0 ? (
          <>
            <Label htmlFor={findingId} className="sr-only">
              Attach to finding
            </Label>
            <select
              id={findingId}
              value={alertId}
              onChange={(event) => setAlertId(event.target.value)}
              className="h-8 max-w-56 rounded-md border bg-background px-2 text-[12px] outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">Whole claim</option>
              {data.findings.map((f) => (
                <option key={f.key} value={f.alert_id}>
                  {f.category_label}
                </option>
              ))}
            </select>
          </>
        ) : (
          <span />
        )}
        <Button type="submit" size="sm" disabled={!text.trim() || addNote.isPending}>
          {addNote.isPending && <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />}
          Add note
        </Button>
      </div>
    </form>
  );
}

function AnalysisSteps({ data }: { data: Investigation }) {
  if (data.analysis_events.length === 0) return null;
  return (
    <div className="border-t px-4 py-3">
      <p className="text-[12px] font-semibold">Analysis steps</p>
      <p className="mb-2 text-[12px] text-muted-foreground">
        Recorded by the analysis pipeline (rules engine, correlation, AI extraction). Not part of the sealed chain.
      </p>
      <ul className="space-y-1.5">
        {data.analysis_events.map((a) => (
          <li key={a.event_id} className="flex items-baseline justify-between gap-3 text-[12px]">
            <span className="min-w-0">
              <span className="font-medium">{a.event_type.replaceAll("_", " ")}</span>{" "}
              <span className="text-muted-foreground">
                {a.entity_type} <span className="num">{a.entity_id}</span>
              </span>
              <span
                className={cn(
                  "ml-1.5 rounded px-1 py-px text-[10px] font-semibold uppercase",
                  a.actor_type === "ai" ? "bg-chart-3/15 text-chart-3" : "bg-muted text-muted-foreground",
                )}
                title={a.model ? `${a.model}${a.prompt_version ? ` · prompt ${a.prompt_version}` : ""}` : undefined}
              >
                {a.actor_type}
              </span>
            </span>
            <time className="num shrink-0 text-muted-foreground" dateTime={a.created_at} title={formatDateTime(a.created_at)}>
              {relativeTime(a.created_at)}
            </time>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EvidenceTimeline({ data }: { data: Investigation }) {
  const [filter, setFilter] = useState<EvidenceFilter>("all");
  const events = data.events.filter((e) => matchesFilter(e, filter));
  const findings = new Map(data.findings.map((f) => [f.key, f.category_label]));
  return (
    <Panel className="xl:sticky xl:top-4">
      <PanelHeader
        title="Evidence history"
        description="Every calculation, decision, override and note, newest first. Entries are never edited."
        actions={<Calculator className="size-4 text-muted-foreground" aria-hidden="true" />}
      />
      <NoteComposer data={data} />
      <div className="flex flex-wrap gap-1 border-b px-4 py-2" role="tablist" aria-label="Filter the history">
        {EVIDENCE_FILTERS.map((f) => {
          const count = data.events.filter((e) => matchesFilter(e, f.value)).length;
          return (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "num rounded-full px-2.5 py-1 text-[12px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
                filter === f.value
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {f.label} <span className="opacity-60">{count}</span>
            </button>
          );
        })}
      </div>
      {events.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-muted-foreground">Nothing recorded of this kind yet.</p>
      ) : (
        <ol className="max-h-[calc(100vh-14rem)] overflow-y-auto px-4 pt-4 pb-2">
          {events.map((event, index) => (
            <TimelineItem key={event.seq} event={event} last={index === events.length - 1} findings={findings} />
          ))}
        </ol>
      )}
      {(filter === "all" || filter === "system") && <AnalysisSteps data={data} />}
    </Panel>
  );
}
