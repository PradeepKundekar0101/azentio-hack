"use client";

import { CircleCheck, CircleX, LoaderCircle, RotateCcw } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import { getErrorMessage } from "@/lib/api/errors";
import { useReviewAlert } from "@/lib/alerts/hooks";
import type { AlertOut, AlertStatus } from "@/lib/alerts/model";

const NOTE_MAX = 2000;

const COPY: Record<AlertStatus, { title: string; description: string; action: string; done: string }> = {
  reviewed: {
    title: "Mark as reviewed",
    description: "Record that this alert was checked. Add what you found or did, so others can follow it.",
    action: "Mark reviewed",
    done: "Alert marked as reviewed",
  },
  dismissed: {
    title: "Dismiss alert",
    description: "Dismiss this alert when it is not leakage. Say why, so the decision can be audited.",
    action: "Dismiss",
    done: "Alert dismissed",
  },
  open: {
    title: "Reopen alert",
    description: "Put this alert back in the open queue.",
    action: "Reopen",
    done: "Alert reopened",
  },
};

/** Mark reviewed, dismiss or reopen, each with an optional note, through one dialog. */
export function ReviewActions({ alert }: { alert: AlertOut }) {
  const [target, setTarget] = useState<AlertStatus | null>(null);
  const [note, setNote] = useState("");
  const review = useReviewAlert(alert.id);
  const noteId = useId();

  const openDialog = (status: AlertStatus) => {
    setNote(status === "open" ? "" : (alert.review_note ?? ""));
    setTarget(status);
  };

  const submit = () => {
    if (!target) return;
    review.mutate(
      { status: target, note: note.trim() || null },
      {
        onSuccess: () => {
          toast.success(COPY[target].done);
          setTarget(null);
        },
        onError: (error) => toast.error(getErrorMessage(error)),
      },
    );
  };

  const copy = target ? COPY[target] : null;

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {alert.status === "open" ? (
          <>
            <Button variant="outline" onClick={() => openDialog("dismissed")}>
              <CircleX data-icon="inline-start" aria-hidden="true" />
              Dismiss
            </Button>
            <Button onClick={() => openDialog("reviewed")}>
              <CircleCheck data-icon="inline-start" aria-hidden="true" />
              Mark reviewed
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={() => openDialog("open")}>
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
            Reopen
          </Button>
        )}
      </div>
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
              <div className="grid gap-1.5">
                <Label htmlFor={noteId} className="text-[13px]">
                  Note <span className="font-normal text-muted-foreground">(optional)</span>
                </Label>
                <Textarea
                  id={noteId}
                  value={note}
                  maxLength={NOTE_MAX}
                  rows={4}
                  className="min-h-24"
                  placeholder={target === "dismissed" ? "For example: provider contract allows a private room" : ""}
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
                <Button type="submit" disabled={review.isPending}>
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
