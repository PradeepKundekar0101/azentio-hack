"use client";

import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import { useMemo, useState } from "react";

import { Panel } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { SelectItem } from "@/components/ui/select";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useConfirmDocument, useProviders, useServiceCodes } from "@/lib/documents/hooks";
import {
  CLAIM_TYPES,
  type ClaimField,
  type ConfirmResult,
  countErrors,
  type Draft,
  draftToForm,
  emptyErrors,
  emptyLine,
  type FormErrors,
  type FormLine,
  formToPayload,
  type InvoiceField,
  mapProblems,
  optionLabel,
  readProblems,
  type ReviewForm as ReviewFormState,
} from "@/lib/documents/model";
import { formatNumber } from "@/lib/format";

import { SelectField, TextField } from "./fields";
import { LineItems, TotalsSummary } from "./line-items";

const CLAIM_TYPE_OPTIONS = CLAIM_TYPES.map((t) => ({ value: t, label: optionLabel(t) }));

function Section({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="@container border-b px-4 py-4 last:border-b-0">
      <h2 id={id} className="text-sm font-semibold">
        {title}
      </h2>
      {description && <p className="mt-0.5 text-[13px] text-pretty text-muted-foreground">{description}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** Focus the first control the server rejected, once React has rendered the errors. */
function focusFirstInvalid() {
  requestAnimationFrame(() => {
    const el = document.querySelector<HTMLElement>("#review-form [aria-invalid='true']");
    if (el) {
      el.focus({ preventScroll: true });
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      document.getElementById("review-errors")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
}

export function ReviewForm({
  documentId,
  draft,
  printedProviderName,
  onConfirmed,
}: {
  documentId: number;
  draft: Draft;
  printedProviderName: string | null;
  onConfirmed: (result: ConfirmResult) => void;
}) {
  const [form, setForm] = useState<ReviewFormState>(() => {
    const initial = draftToForm(draft);
    // A draft with no lines still needs one to fill in.
    return initial.lines.length > 0 ? initial : { ...initial, lines: [emptyLine(initial.claim.incident_date)] };
  });
  const [errors, setErrors] = useState<FormErrors>(emptyErrors);
  const [failure, setFailure] = useState<string | null>(null);

  const providers = useProviders();
  const codes = useServiceCodes();
  const confirm = useConfirmDocument(documentId);
  const busy = confirm.isPending;

  const providerOptions = useMemo(
    () =>
      (providers.data?.items ?? []).map((p) => ({ value: p.provider_id, label: `${p.name}, ${p.city}` })),
    [providers.data],
  );
  const providerById = useMemo(
    () => new Map((providers.data?.items ?? []).map((p) => [p.provider_id, p])),
    [providers.data],
  );

  const setClaim = (field: ClaimField, value: string) => {
    setForm((f) => ({ ...f, claim: { ...f.claim, [field]: value } }));
    setErrors((e) => {
      if (!e.claim[field]) return e;
      const claim = { ...e.claim };
      delete claim[field];
      return { ...e, claim };
    });
  };

  const setInvoice = (field: InvoiceField, value: string, extra: Partial<ReviewFormState> = {}) => {
    setForm((f) => ({ ...f, [field]: value, ...extra }));
    setErrors((e) => {
      const invoice = { ...e.invoice };
      delete invoice[field];
      if (field === "provider_id") delete invoice.provider_name;
      return { ...e, invoice };
    });
  };

  const setLine = (key: string, patch: Partial<FormLine>) => {
    setForm((f) => ({ ...f, lines: f.lines.map((l) => (l.key === key ? { ...l, ...patch } : l)) }));
    setErrors((e) => {
      const current = e.lines[key];
      if (!current) return e;
      const next = { ...current };
      for (const field of Object.keys(patch)) delete next[field as keyof typeof next];
      return { ...e, lines: { ...e.lines, [key]: next } };
    });
  };

  // Line errors are mapped by row position, so a stale set would point at the wrong lines.
  const clearLineErrors = () => setErrors((e) => ({ ...e, lines: {}, general: [] }));

  const addLine = () => {
    const last = form.lines.at(-1);
    setForm((f) => ({ ...f, lines: [...f.lines, emptyLine(last?.service_date ?? f.claim.incident_date)] }));
    clearLineErrors();
  };

  const removeLine = (key: string) => {
    setForm((f) => ({ ...f, lines: f.lines.filter((l) => l.key !== key) }));
    clearLineErrors();
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setFailure(null);
    const keys = form.lines.map((l) => l.key);
    confirm.mutate(formToPayload(form), {
      onSuccess: (result) => {
        setErrors(emptyErrors());
        onConfirmed(result);
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 422 && error.code === "validation_failed") {
          const mapped = mapProblems(readProblems(error.details), keys);
          setErrors(mapped);
          setFailure(error.message);
          focusFirstInvalid();
          return;
        }
        setErrors(emptyErrors());
        setFailure(getErrorMessage(error));
        focusFirstInvalid();
      },
    });
  };

  const errorCount = countErrors(errors);
  const score = draft.provider_match_score;
  const selectedProvider = providerById.get(form.provider_id);
  const providerHint =
    form.provider_id && form.provider_id === draft.provider_id && score !== null ? (
      <>
        Matched from the printed name
        {printedProviderName && printedProviderName !== selectedProvider?.name && (
          <>
            {" "}
            <span className="text-foreground">&ldquo;{printedProviderName}&rdquo;</span>
          </>
        )}{" "}
        · <span className="num">{Math.round(score)}%</span> similar
      </>
    ) : !form.provider_id && (printedProviderName || draft.provider_name) ? (
      <span className="text-warning">
        No provider matched &ldquo;{printedProviderName ?? draft.provider_name}&rdquo;
        {score ? (
          <>
            {" "}
            (best <span className="num">{Math.round(score)}%</span>)
          </>
        ) : null}
        . Choose one.
      </span>
    ) : undefined;

  return (
    <Panel>
      <form id="review-form" noValidate onSubmit={submit} aria-describedby={failure ? "review-errors" : undefined}>
        <fieldset disabled={busy} className="min-w-0">
          <Section id="claim-title" title="Claim" description="Who is claiming, under which policy, and for how much.">
            <div className="grid gap-x-3 gap-y-3 @md:grid-cols-2">
              <TextField
                id="policy_number"
                label="Policy number"
                value={form.claim.policy_number}
                error={errors.claim.policy_number}
                missing={!form.claim.policy_number}
                onChange={(v) => setClaim("policy_number", v)}
              />
              <TextField
                id="claimant_id"
                label="Claimant ID"
                value={form.claim.claimant_id}
                error={errors.claim.claimant_id}
                missing={!form.claim.claimant_id}
                hint={!form.claim.claimant_id ? "Member ID on the policy. Not printed on invoices." : undefined}
                onChange={(v) => setClaim("claimant_id", v)}
              />
              <TextField
                id="claimant_name"
                label="Claimant name"
                value={form.claim.claimant_name}
                error={errors.claim.claimant_name}
                missing={!form.claim.claimant_name}
                onChange={(v) => setClaim("claimant_name", v)}
              />
              <SelectField
                id="claim_type"
                label="Claim type"
                placeholder="Choose a claim type"
                value={form.claim.claim_type}
                options={CLAIM_TYPE_OPTIONS}
                error={errors.claim.claim_type}
                missing={!form.claim.claim_type}
                onChange={(v) => setClaim("claim_type", v)}
              />
              <TextField
                id="incident_date"
                label="Incident date"
                type="date"
                value={form.claim.incident_date}
                error={errors.claim.incident_date}
                missing={!form.claim.incident_date}
                onChange={(v) => setClaim("incident_date", v)}
              />
              <TextField
                id="submission_date"
                label="Submission date"
                type="date"
                value={form.claim.submission_date}
                error={errors.claim.submission_date}
                missing={!form.claim.submission_date}
                onChange={(v) => setClaim("submission_date", v)}
              />
              <TextField
                id="requested_amount"
                label="Requested amount"
                inputMode="decimal"
                prefix="₹"
                inputClassName="num"
                value={form.claim.requested_amount}
                error={errors.claim.requested_amount}
                missing={!form.claim.requested_amount}
                onChange={(v) => setClaim("requested_amount", v)}
              />
              <TextField
                id="incident_reference"
                label="Incident reference"
                optional
                value={form.claim.incident_reference}
                error={errors.claim.incident_reference}
                onChange={(v) => setClaim("incident_reference", v)}
              />
            </div>
          </Section>

          <Section id="invoice-title" title="Invoice" description="The bill and the provider that issued it.">
            <div className="grid gap-x-3 gap-y-3 @md:grid-cols-2">
              <TextField
                id="invoice_reference"
                label="Invoice reference"
                value={form.invoice_reference}
                error={errors.invoice.invoice_reference}
                missing={!form.invoice_reference}
                onChange={(v) => setInvoice("invoice_reference", v)}
              />
              <SelectField
                id="provider_id"
                label="Provider"
                placeholder={providers.isPending ? "Loading providers" : "Choose a provider"}
                value={form.provider_id}
                error={errors.invoice.provider_id ?? errors.invoice.provider_name}
                hint={providerHint}
                missing={!form.provider_id}
                onChange={(v) => setInvoice("provider_id", v, { provider_name: providerById.get(v)?.name ?? "" })}
              >
                {providerOptions.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectField>
            </div>
          </Section>

          <Section
            id="lines-title"
            title="Line items"
            description="Each service billed. Every line needs a service code from the reference list."
          >
            <LineItems
              lines={form.lines}
              errors={errors.lines}
              codes={codes.data?.items ?? []}
              codesLoading={codes.isPending}
              disabled={busy}
              onChange={setLine}
              onAdd={addLine}
              onRemove={removeLine}
            />
            <div className="mt-4">
              <TotalsSummary lines={form.lines} requested={form.claim.requested_amount} />
            </div>
          </Section>
        </fieldset>

        <div className="sticky bottom-0 z-10 space-y-3 rounded-b-lg border-t bg-card/95 px-4 py-3 backdrop-blur-sm supports-backdrop-filter:bg-card/85">
          {failure && (
            <Alert id="review-errors" variant="destructive">
              <CircleAlert aria-hidden="true" />
              <AlertTitle>
                {errorCount > 0
                  ? errorCount === 1
                    ? "1 problem to fix before confirming"
                    : `${formatNumber(errorCount)} problems to fix before confirming`
                  : "The claim was not confirmed"}
              </AlertTitle>
              <AlertDescription className="break-words">
                {errors.general.length > 0 ? (
                  <ul className="list-disc space-y-0.5 pl-4">
                    {errors.general.map((m) => (
                      <li key={m}>{m}</li>
                    ))}
                  </ul>
                ) : errorCount > 0 ? (
                  "Each problem is shown next to its field."
                ) : (
                  failure
                )}
              </AlertDescription>
            </Alert>
          )}
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <p className="hidden text-[13px] text-muted-foreground sm:block">
              Confirming checks the claim like an imported row, then processes it.
            </p>
            <Button type="submit" disabled={busy} className="ml-auto">
              {busy ? (
                <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />
              ) : (
                <CircleCheck data-icon="inline-start" aria-hidden="true" />
              )}
              {busy ? "Confirming" : "Confirm claim"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}
