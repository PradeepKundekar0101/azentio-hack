"use client";

import { CircleCheck, Plus, Trash2, TriangleAlert } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectGroup, SelectItem, SelectLabel } from "@/components/ui/select";
import {
  CATEGORIES,
  type FormLine,
  type LineField,
  lineProductMismatch,
  optionLabel,
  paiseToAmount,
  type ServiceCode,
  sumLines,
  TOTAL_TOLERANCE_PAISE,
} from "@/lib/documents/model";
import { formatINR, formatNumber, formatPercent, toPaise } from "@/lib/format";
import { cn } from "@/lib/utils";

import { SelectField, TextField } from "./fields";

const CATEGORY_OPTIONS = CATEGORIES.map((c) => ({ value: c, label: optionLabel(c) }));

export function CodeMatchBadge({ line }: { line: FormLine }) {
  if (!line.service_code) return <Badge variant="warning">Needs a code</Badge>;
  if (line.origin === "printed_code") return <Badge variant="success">Printed code</Badge>;
  if (line.origin === "description") {
    return (
      <Badge variant="secondary" className="font-normal">
        Matched by description{" "}
        {line.confidence !== null && <span className="num font-medium">{formatPercent(line.confidence, { digits: 0 })}</span>}
      </Badge>
    );
  }
  if (line.origin === "manual") {
    return (
      <Badge variant="outline" className="font-normal text-muted-foreground">
        Chosen by you
      </Badge>
    );
  }
  return null;
}

/** Service codes grouped by category, in reference order. */
function useCodeGroups(codes: ServiceCode[]) {
  return useMemo(() => {
    const groups = new Map<string, ServiceCode[]>();
    for (const code of codes) {
      const list = groups.get(code.category) ?? [];
      list.push(code);
      groups.set(code.category, list);
    }
    return [...groups.entries()];
  }, [codes]);
}

export function LineItems({
  lines,
  errors,
  codes,
  codesLoading,
  disabled,
  onChange,
  onAdd,
  onRemove,
}: {
  lines: FormLine[];
  errors: Record<string, Partial<Record<LineField, string>>>;
  codes: ServiceCode[];
  codesLoading: boolean;
  disabled: boolean;
  onChange: (key: string, patch: Partial<FormLine>) => void;
  onAdd: () => void;
  onRemove: (key: string) => void;
}) {
  const groups = useCodeGroups(codes);
  const byCode = useMemo(() => new Map(codes.map((c) => [c.code, c])), [codes]);

  return (
    <div className="space-y-3">
      <ol className="space-y-3" aria-label="Line items">
        {lines.map((line, index) => {
          const lineErrors = errors[line.key] ?? {};
          const id = (field: string) => `${line.key}-${field}`;
          const mismatch = lineProductMismatch(line);
          const known = !line.service_code || byCode.has(line.service_code) || codesLoading;
          return (
            <li
              key={line.key}
              aria-label={`Line ${index + 1}`}
              className={cn(
                "@container rounded-lg border bg-card",
                Object.keys(lineErrors).length > 0 && "border-destructive/40",
              )}
            >
              <div className="flex min-h-10 items-center gap-2 border-b py-1.5 pr-1.5 pl-3">
                <span className="num text-[13px] font-semibold">Line {index + 1}</span>
                <CodeMatchBadge line={line} />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="ml-auto text-muted-foreground hover:text-destructive"
                  aria-label={`Remove line ${index + 1}`}
                  disabled={disabled || lines.length === 1}
                  onClick={() => onRemove(line.key)}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-3 p-3 @lg:grid-cols-4">
                <TextField
                  id={id("service_description")}
                  label="Description"
                  className="col-span-2 @lg:col-span-4"
                  value={line.service_description}
                  error={lineErrors.service_description}
                  onChange={(v) => onChange(line.key, { service_description: v })}
                />
                <SelectField
                  id={id("service_code")}
                  label="Service code"
                  className="col-span-2"
                  placeholder={codesLoading ? "Loading codes" : "Choose a code"}
                  value={known ? line.service_code : ""}
                  error={
                    lineErrors.service_code ??
                    (!known ? `${line.service_code} is not in the reference list. Choose a code.` : undefined)
                  }
                  onChange={(code) =>
                    onChange(line.key, {
                      service_code: code,
                      category: byCode.get(code)?.category ?? line.category,
                      origin: "manual",
                      confidence: null,
                    })
                  }
                >
                  {groups.map(([category, list]) => (
                    <SelectGroup key={category}>
                      <SelectLabel>{optionLabel(category)}</SelectLabel>
                      {list.map((c) => (
                        <SelectItem key={c.code} value={c.code}>
                          <span className="font-medium">{c.code}</span>{" "}
                          <span className="truncate text-muted-foreground">{c.description}</span>
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ))}
                </SelectField>
                <SelectField
                  id={id("category")}
                  label="Category"
                  className="col-span-2"
                  placeholder="Choose a category"
                  value={line.category}
                  options={CATEGORY_OPTIONS}
                  error={lineErrors.category}
                  onChange={(v) => onChange(line.key, { category: v })}
                />
                <TextField
                  id={id("service_date")}
                  label="Service date"
                  type="date"
                  className="col-span-2 @2xs:col-span-1"
                  value={line.service_date}
                  error={lineErrors.service_date}
                  missing={!line.service_date}
                  onChange={(v) => onChange(line.key, { service_date: v })}
                />
                <TextField
                  id={id("quantity")}
                  label="Quantity"
                  inputMode="decimal"
                  className="col-span-2 @2xs:col-span-1"
                  inputClassName="num"
                  value={line.quantity}
                  error={lineErrors.quantity}
                  onChange={(v) => onChange(line.key, { quantity: v })}
                />
                <TextField
                  id={id("unit_price")}
                  label="Unit price"
                  inputMode="decimal"
                  prefix="₹"
                  className="col-span-2 @2xs:col-span-1"
                  inputClassName="num"
                  value={line.unit_price}
                  error={lineErrors.unit_price}
                  onChange={(v) => onChange(line.key, { unit_price: v })}
                />
                <TextField
                  id={id("line_amount")}
                  label="Amount"
                  inputMode="decimal"
                  prefix="₹"
                  className="col-span-2 @2xs:col-span-1"
                  inputClassName="num"
                  value={line.line_amount}
                  error={lineErrors.line_amount}
                  hint={
                    mismatch !== null ? (
                      <span className="text-warning">
                        {line.quantity.trim()} × {formatINR(line.unit_price.replace(/,/g, ""))} ={" "}
                        {formatINR(paiseToAmount(mismatch))}
                      </span>
                    ) : undefined
                  }
                  onChange={(v) => onChange(line.key, { line_amount: v })}
                />
              </div>
            </li>
          );
        })}
      </ol>
      <Button type="button" variant="outline" size="sm" onClick={onAdd} disabled={disabled}>
        <Plus data-icon="inline-start" aria-hidden="true" />
        Add line
      </Button>
    </div>
  );
}

/** Lines total against the requested amount, with the same ±₹1 tolerance as the backend. */
export function TotalsSummary({ lines, requested }: { lines: FormLine[]; requested: string }) {
  const { paise, missing } = sumLines(lines);
  const requestedPaise = toPaise(requested.trim().replace(/[,\s₹]/g, "") || null);
  const diff = requestedPaise === null ? null : paise - requestedPaise;
  const matches = diff !== null && diff <= TOTAL_TOLERANCE_PAISE && diff >= -TOTAL_TOLERANCE_PAISE;
  const abs = diff === null ? null : diff < BigInt(0) ? -diff : diff;

  return (
    <div className="rounded-lg border bg-muted/30 px-3 py-2.5" aria-live="polite">
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[13px]">
        <dt className="text-muted-foreground">
          Lines total
          {lines.length > 0 && (
            <span className="num">
              {" "}
              ({formatNumber(lines.length)} {lines.length === 1 ? "line" : "lines"})
            </span>
          )}
        </dt>
        <dd className="num text-right font-medium">{formatINR(paiseToAmount(paise))}</dd>
        <dt className="text-muted-foreground">Requested amount</dt>
        <dd className="num text-right font-medium">
          {requestedPaise === null ? <span className="text-muted-foreground">Not set</span> : formatINR(paiseToAmount(requestedPaise))}
        </dd>
      </dl>
      <div className="mt-2 border-t pt-2 text-[13px]">
        {diff === null ? (
          <p className="text-muted-foreground">Enter the requested amount to compare it with the lines.</p>
        ) : matches ? (
          <p className="flex items-center gap-1.5 font-medium text-success">
            <CircleCheck className="size-3.5 shrink-0" aria-hidden="true" />
            Lines add up to the requested amount
          </p>
        ) : (
          <p className="flex items-start gap-1.5 font-medium text-warning">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>
              Lines are <span className="num">{formatINR(paiseToAmount(abs!))}</span>{" "}
              {diff > BigInt(0) ? "more" : "less"} than the requested amount
            </span>
          </p>
        )}
        {missing > 0 && (
          <p className="mt-1 text-muted-foreground">
            <span className="num">{formatNumber(missing)}</span> {missing === 1 ? "line has" : "lines have"} no amount yet.
          </p>
        )}
      </div>
    </div>
  );
}
