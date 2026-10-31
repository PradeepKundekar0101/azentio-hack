"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getErrorMessage } from "@/lib/api/errors";
import { useOverrideCorrection } from "@/lib/evidence/hooks";
import type { EvidenceFinding } from "@/lib/evidence/model";
import { formatINR } from "@/lib/format";

const REASON_MAX = 2000;
const AMOUNT_RE = /^\d{1,10}(\.\d{1,2})?$/;

/** Change the correction applied for one finding. The original recommendation is kept on record. */
export function OverrideDialog({
  claimId,
  finding,
  open,
  onOpenChange,
}: {
  claimId: string;
  finding: EvidenceFinding;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const original = finding.original_recommendation ?? finding.recommendation;
  const [amount, setAmount] = useState(finding.effective_correction ?? "");
  const [reason, setReason] = useState("");
  const override = useOverrideCorrection(claimId);
  const amountId = useId();
  const reasonId = useId();

  const cleaned = amount.replaceAll(",", "").trim();
  const ceiling = Number(original.original_amount);
  const amountValid = AMOUNT_RE.test(cleaned) && Number(cleaned) <= ceiling;
  const reasonValid = reason.trim().length >= 5;
  const corrected = amountValid ? Math.max(0, ceiling - Number(cleaned)).toFixed(2) : null;

  const close = (next: boolean) => {
    if (override.isPending) return;
    if (!next) {
      setAmount(finding.effective_correction ?? "");
      setReason("");
    }
    onOpenChange(next);
  };

  const submit = () => {
    if (!amountValid || !reasonValid) return;
    override.mutate(
      { alertId: finding.alert_id, correction: cleaned, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success("Override recorded. The original recommendation stays on record.");
          close(false);
        },
        onError: (error) => toast.error(getErrorMessage(error)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>Override the recommended correction</DialogTitle>
            <DialogDescription>
              {finding.category_label}. The system&apos;s recommendation is never replaced: it stays in the evidence
              history next to your figure and your reason.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-lg border bg-muted/40 p-3 text-[13px]">
            <div>
              <p className="text-muted-foreground">Recommended</p>
              <p className="num text-base font-semibold">{formatINR(original.correction)}</p>
              <p className="text-[12px] text-muted-foreground">{original.rule_or_pattern}</p>
            </div>
            <ArrowRight className="size-4 text-muted-foreground" aria-hidden="true" />
            <div>
              <p className="text-muted-foreground">Your correction</p>
              <p className="num text-base font-semibold">{amountValid ? formatINR(cleaned) : "–"}</p>
              <p className="num text-[12px] text-muted-foreground">
                Pays {corrected ? formatINR(corrected) : "–"} of {formatINR(original.original_amount)}
              </p>
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor={amountId} className="text-[13px]">
              Correction to apply (₹)
            </Label>
            <Input
              id={amountId}
              inputMode="decimal"
              autoComplete="off"
              value={amount}
              aria-invalid={amount !== "" && !amountValid}
              onChange={(event) => setAmount(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Between ₹0 and {formatINR(original.original_amount)} ({original.basis}). Enter the recommended{" "}
              {formatINR(original.correction)} to restore it.
            </p>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor={reasonId} className="text-[13px]">
              Reason <span className="font-normal text-muted-foreground">(required)</span>
            </Label>
            <Textarea
              id={reasonId}
              value={reason}
              maxLength={REASON_MAX}
              rows={3}
              className="min-h-20"
              placeholder="For example: provider refunded ₹1,500 directly to the member"
              onChange={(event) => setReason(event.target.value)}
            />
            <p className="num text-right text-xs text-muted-foreground">
              {reason.length} / {REASON_MAX}
            </p>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" disabled={override.isPending} onClick={() => close(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={override.isPending || !amountValid || !reasonValid}>
              {override.isPending && <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />}
              Record override
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
