"use client";

import { ArrowUpRight, CircleCheck, CircleX, FileQuestion, LoaderCircle, Lock, RotateCcw } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { getErrorMessage } from "@/lib/api/errors";
import { useReviewAlert } from "@/lib/alerts/hooks";
import {
  type AlertOut,
  type AlertStatus,
  ESCALATION_TARGET_LABELS,
  type EscalationTarget,
  escalationTargetLabel,
} from "@/lib/alerts/model";
import { useMe } from "@/lib/auth/hooks";
import { canDecideEscalation, escalationTargetsFor } from "@/lib/auth/permissions";

const NOTE_MAX = 2000;

interface Copy {
  title: string;
  description: string;
  action: string;
  done: string;
  /** The backend refuses these decisions without a note, so the form does too. */
  noteRequired: boolean;
  placeholder?: string;
}

const COPY: Record<AlertStatus, Copy> = {
  reviewed: {
    title: "Confirm discrepancy",
    description: "Record that this finding was checked and stands. Add what you found, so others can follow it.",
    action: "Confirm",
    done: "Alert confirmed",
    noteRequired: false,
  },
  dismissed: {
    title: "Mark as false positive",
    description: "Dismiss this alert when it is not leakage. The reason is required and is kept in the audit trail.",
    action: "Dismiss",
    done: "Alert dismissed as a false positive",
    noteRequired: true,
    placeholder: "For example: provider contract allows a private room",
  },
  evidence_requested: {
    title: "Request additional evidence",
    description: "Say what is missing. The alert stays open and shows that evidence was asked for.",
    action: "Request evidence",
    done: "Evidence requested",
    noteRequired: true,
    placeholder: "For example: discharge summary and the original pharmacy bill",
  },
  escalated: {
    title: "Escalate",
    description:
      "Hand this alert to a higher level. That level, or anyone above it, decides it; you will not be able to decide it yourself afterwards.",
    action: "Escalate",
    done: "Alert escalated",
    noteRequired: true,
    placeholder: "Why this needs a senior decision",
  },
  open: {
    title: "Reopen alert",
    description: "Put this alert back in the open queue.",
    action: "Reopen",
    done: "Alert reopened",
    noteRequired: false,
  },
};

/**
 * The analyst's decisions on a finding: confirm, false positive, request evidence, escalate, reopen.
 * An escalated alert is decided only by a senior claims reviewer or an admin, and never by whoever
 * escalated it; everyone else sees why the buttons are not there.
 */
export function ReviewActions({ alert }: { alert: AlertOut }) {
  const [target, setTarget] = useState<AlertStatus | null>(null);
  const [note, setNote] = useState("");
  const review = useReviewAlert(alert.id);
  const { data: me } = useMe();
  const targets = escalationTargetsFor(me?.role) as EscalationTarget[];
  const [escalateTo, setEscalateTo] = useState<EscalationTarget>("senior_reviewer");
  const chosenTarget = targets.includes(escalateTo) ? escalateTo : targets[0];
  const noteId = useId();
  const targetId = useId();

  const openDialog = (status: AlertStatus) => {
    setNote(status === "open" || status === "escalated" ? "" : (alert.review_note ?? ""));
    setTarget(status);
  };

  const copy = target ? COPY[target] : null;
  const noteMissing = copy?.noteRequired === true && note.trim().length === 0;

  const submit = () => {
    if (!target || noteMissing) return;
    review.mutate(
      { status: target, note: note.trim() || null, escalate_to: target === "escalated" ? (chosenTarget ?? null) : null },
      {
        onSuccess: () => {
          toast.success(COPY[target].done);
          setTarget(null);
        },
        onError: (error) => toast.error(getErrorMessage(error)),
      },
    );
  };

  let buttons: React.ReactNode;
  if (alert.status === "escalated") {
    if (!me) {
      buttons = null;
    } else if (canDecideEscalation(me.role, me.username, alert.escalated_by, alert.escalated_to)) {
      buttons = (
        <>
          {targets.length > 0 && (
            <Button variant="outline" onClick={() => openDialog("escalated")}>
              <ArrowUpRight data-icon="inline-start" aria-hidden="true" />
              Escalate higher
            </Button>
          )}
          <Button variant="outline" onClick={() => openDialog("open")}>
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
            Send back
          </Button>
          <Button variant="outline" onClick={() => openDialog("dismissed")}>
            <CircleX data-icon="inline-start" aria-hidden="true" />
            False positive
          </Button>
          <Button onClick={() => openDialog("reviewed")}>
            <CircleCheck data-icon="inline-start" aria-hidden="true" />
            Confirm
          </Button>
        </>
      );
    } else {
      buttons = (
        <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
          <Lock className="size-3.5" aria-hidden="true" />
          {alert.escalated_by === me.username
            ? "You escalated this; another reviewer decides it."
            : `Awaiting ${escalationTargetLabel(alert.escalated_to ?? "senior_reviewer").toLowerCase()} decision.`}
        </p>
      );
    }
  } else if (alert.status === "open" || alert.status === "evidence_requested") {
    buttons = (
      <>
        {targets.length > 0 && (
          <Button variant="outline" onClick={() => openDialog("escalated")}>
            <ArrowUpRight data-icon="inline-start" aria-hidden="true" />
            Escalate
          </Button>
        )}
        {alert.status === "open" && (
          <Button variant="outline" onClick={() => openDialog("evidence_requested")}>
            <FileQuestion data-icon="inline-start" aria-hidden="true" />
            Request evidence
          </Button>
        )}
        <Button variant="outline" onClick={() => openDialog("dismissed")}>
          <CircleX data-icon="inline-start" aria-hidden="true" />
          False positive
        </Button>
        <Button onClick={() => openDialog("reviewed")}>
          <CircleCheck data-icon="inline-start" aria-hidden="true" />
          Confirm
        </Button>
      </>
    );
  } else {
    buttons = (
      <Button variant="outline" onClick={() => openDialog("open")}>
        <RotateCcw data-icon="inline-start" aria-hidden="true" />
        Reopen
      </Button>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">{buttons}</div>
      <Dialog open={target !== null} onOpenChange={(open) => !open && !review.isPending && setTarget(null)}>
        <DialogContent className="sm:max-w-md">
          {copy && (
            <form
              className="grid gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                submit();
              }}
            >
              <DialogHeader>
                <DialogTitle>{copy.title}</DialogTitle>
                <DialogDescription>{copy.description}</DialogDescription>
              </DialogHeader>
              {target === "escalated" && (
                <div className="grid gap-1.5">
                  <Label htmlFor={targetId} className="text-[13px]">
                    Escalate to
                  </Label>
                  <Select value={chosenTarget} onValueChange={(value) => setEscalateTo(value as EscalationTarget)}>
                    <SelectTrigger id={targetId} className="w-full bg-card">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent position="popper" align="start">
                      {targets.map((value) => (
                        <SelectItem key={value} value={value}>
                          {ESCALATION_TARGET_LABELS[value]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="grid gap-1.5">
                <Label htmlFor={noteId} className="text-[13px]">
                  {target === "escalated" || target === "dismissed" ? "Reason" : "Note"}{" "}
                  {!copy.noteRequired && <span className="font-normal text-muted-foreground">(optional)</span>}
                </Label>
                <Textarea
                  id={noteId}
                  value={note}
                  maxLength={NOTE_MAX}
                  rows={4}
                  required={copy.noteRequired}
                  className="min-h-24"
                  placeholder={copy.placeholder}
                  onChange={(event) => setNote(event.target.value)}
                />
                <p className="num text-right text-xs text-muted-foreground">
                  {note.length} / {NOTE_MAX}
                </p>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" disabled={review.isPending} onClick={() => setTarget(null)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={review.isPending || noteMissing}>
                  {review.isPending && (
                    <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />
                  )}
                  {copy.action}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
