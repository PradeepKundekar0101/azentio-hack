"use client";

import { ChevronDown, FilterX, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  type AlertFilters,
  countActiveFilters,
  EMPTY_FILTERS,
  type ListFilterKey,
  parseAmount,
  parseIsoDate,
  rangeProblems,
} from "@/lib/alerts/filters";
import { useProviders } from "@/lib/alerts/hooks";
import {
  ALERT_STATUSES,
  alertStatusLabel,
  AMOUNT_TYPES,
  amountTypeLabel,
  CATEGORIES,
  categoryLabel,
  CLAIM_TYPES,
  claimTypeLabel,
  SEVERITIES,
  severityLabel,
} from "@/lib/alerts/model";
import { formatDate, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Option {
  value: string;
  label: string;
}

const options = (values: readonly string[], label: (v: string) => string): Option[] =>
  values.map((value) => ({ value, label: label(value) }));

const STATIC_OPTIONS: Record<Exclude<ListFilterKey, "provider_id">, Option[]> = {
  claim_type: options(CLAIM_TYPES, claimTypeLabel),
  category: options(CATEGORIES, categoryLabel),
  severity: options(SEVERITIES, severityLabel),
  amount_type: options(AMOUNT_TYPES, amountTypeLabel),
  status: options(ALERT_STATUSES, alertStatusLabel),
};

const LIST_LABELS: Record<ListFilterKey, string> = {
  claim_type: "Claim type",
  provider_id: "Provider",
  category: "Category",
  severity: "Severity",
  amount_type: "Amount type",
  status: "Status",
};

/** Provider names by ID, for filter labels and chips. Falls back to the ID. */
export function useProviderOptions(): Option[] {
  const providers = useProviders();
  return (providers.data?.items ?? []).map((p) => ({ value: p.provider_id, label: p.name }));
}

function amountRangeText(min: string, max: string): string {
  if (min && max) return `${formatINR(min)}–${formatINR(max)}`;
  if (min) return `From ${formatINR(min)}`;
  return `Up to ${formatINR(max)}`;
}

function dateRangeText(from: string, to: string): string {
  if (from && to) return `${formatDate(from)} – ${formatDate(to)}`;
  if (from) return `From ${formatDate(from)}`;
  return `Up to ${formatDate(to)}`;
}

/** Filter controls for alerts. Every change goes straight to `onChange`, which keeps it in the URL. */
export function AlertFilterBar({
  filters,
  onChange,
  className,
}: {
  filters: AlertFilters;
  onChange: (next: AlertFilters) => void;
  className?: string;
}) {
  const providerOptions = useProviderOptions();
  const active = countActiveFilters(filters);
  const listOptions = (key: ListFilterKey) => (key === "provider_id" ? providerOptions : STATIC_OPTIONS[key]);

  return (
    <div role="group" aria-label="Filter alerts" className={cn("flex flex-wrap items-center gap-2", className)}>
      {(["claim_type", "provider_id", "category", "severity", "amount_type", "status"] as const).map((key) => (
        <MultiFilter
          key={key}
          label={LIST_LABELS[key]}
          values={filters[key]}
          options={listOptions(key)}
          onChange={(values) => onChange({ ...filters, [key]: values })}
        />
      ))}
      <AmountRangeFilter
        min={filters.amount_min}
        max={filters.amount_max}
        onChange={(amount_min, amount_max) => onChange({ ...filters, amount_min, amount_max })}
      />
      <DateRangeFilter
        from={filters.date_from}
        to={filters.date_to}
        onChange={(date_from, date_to) => onChange({ ...filters, date_from, date_to })}
      />
      {active > 0 && (
        <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_FILTERS)}>
          <FilterX data-icon="inline-start" aria-hidden="true" />
          Clear all
        </Button>
      )}
    </div>
  );
}

function FilterTrigger({
  label,
  value,
  active,
  className,
  ...props
}: { label: string; value: string; active: boolean } & React.ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "flex h-7 max-w-full min-w-0 items-center gap-1.5 rounded-[min(var(--radius-md),10px)] border border-input bg-card pr-2 pl-2.5 text-[13px] whitespace-nowrap transition-colors outline-none select-none hover:bg-muted/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-expanded:bg-muted/60 dark:bg-input/30 dark:hover:bg-input/50",
        active && "border-primary/50",
        className,
      )}
      {...props}
    >
      <span className="text-muted-foreground">{label}:</span>
      <span className={cn("min-w-0 truncate", active && "font-medium")}>{value}</span>
      <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
    </button>
  );
}

function MultiFilter({
  label,
  values,
  options,
  onChange,
}: {
  label: string;
  values: string[];
  options: Option[];
  onChange: (values: string[]) => void;
}) {
  // While the menu is open the selection is held here, so quick successive clicks build on each
  // other instead of on a URL that has not caught up yet.
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(values);
  const selected = open ? draft : values;
  const names = new Map(options.map((o) => [o.value, o.label]));
  const summary =
    selected.length === 0
      ? "All"
      : selected.length === 1
        ? (names.get(selected[0]) ?? selected[0])
        : `${selected.length} selected`;
  const toggle = (value: string, checked: boolean) => {
    const next = checked ? [...selected, value] : selected.filter((v) => v !== value);
    setDraft(next);
    onChange(next);
  };
  const clear = () => {
    setDraft([]);
    onChange([]);
  };

  return (
    <DropdownMenu
      modal={false}
      open={open}
      onOpenChange={(next) => {
        setDraft(values);
        setOpen(next);
      }}
    >
      <DropdownMenuTrigger asChild>
        <FilterTrigger
          label={label}
          value={summary}
          active={selected.length > 0}
          aria-label={`${label}: ${selected.length === 0 ? "all" : selected.map((v) => names.get(v) ?? v).join(", ")}`}
          className="max-w-64"
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-auto max-w-80 min-w-48">
        {options.length === 0 ? (
          <p className="px-1.5 py-1 text-[13px] text-muted-foreground">Loading</p>
        ) : (
          options.map((option) => (
            <DropdownMenuCheckboxItem
              key={option.value}
              checked={selected.includes(option.value)}
              onCheckedChange={(checked) => toggle(option.value, checked === true)}
              // Keep the menu open so several values can be picked in one go.
              onSelect={(event) => event.preventDefault()}
              className="text-[13px]"
            >
              {option.label}
            </DropdownMenuCheckboxItem>
          ))
        )}
        {selected.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-[13px] text-muted-foreground" onSelect={clear}>
              Clear {label.toLowerCase()}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function RangePopover({
  label,
  summary,
  active,
  children,
  open,
  onOpenChange,
}: {
  label: string;
  summary: string;
  active: boolean;
  children: React.ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <FilterTrigger label={label} value={summary} active={active} aria-label={`${label}: ${summary}`} />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(20rem,calc(100vw-2rem))] gap-3 p-3">
        {children}
      </PopoverContent>
    </Popover>
  );
}

function RangeForm({
  first,
  second,
  error,
  onApply,
  onClear,
  canClear,
}: {
  first: React.ReactNode;
  second: React.ReactNode;
  error: string | null;
  onApply: () => void;
  onClear: () => void;
  canClear: boolean;
}) {
  return (
    <form
      className="space-y-3"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onApply();
      }}
    >
      <div className="grid grid-cols-2 gap-2">
        {first}
        {second}
      </div>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        {canClear && (
          <Button type="button" variant="ghost" size="sm" onClick={onClear}>
            <X data-icon="inline-start" aria-hidden="true" />
            Clear
          </Button>
        )}
        <Button type="submit" size="sm">
          Apply
        </Button>
      </div>
    </form>
  );
}

function Field({ id, label, ...props }: { id: string; label: string } & React.ComponentProps<typeof Input>) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </Label>
      <Input id={id} className="h-8 text-[13px] md:text-[13px]" {...props} />
    </div>
  );
}

function AmountRangeFilter({
  min,
  max,
  onChange,
}: {
  min: string;
  max: string;
  onChange: (min: string, max: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ min, max });
  const [error, setError] = useState<string | null>(null);
  const active = Boolean(min || max);

  const onOpenChange = (next: boolean) => {
    if (next) {
      setDraft({ min, max });
      setError(null);
    }
    setOpen(next);
  };

  const apply = () => {
    const nextMin = draft.min.trim() ? parseAmount(draft.min) : "";
    const nextMax = draft.max.trim() ? parseAmount(draft.max) : "";
    if ((draft.min.trim() && !nextMin) || (draft.max.trim() && !nextMax)) {
      setError("Enter amounts in rupees, for example 5000 or 2,500.50.");
      return;
    }
    if (rangeProblems({ ...EMPTY_FILTERS, amount_min: nextMin, amount_max: nextMax }).amount) {
      setError("The minimum is above the maximum.");
      return;
    }
    onChange(nextMin, nextMax);
    setOpen(false);
  };

  return (
    <RangePopover
      label="Amount"
      summary={active ? amountRangeText(min, max) : "Any"}
      active={active}
      open={open}
      onOpenChange={onOpenChange}
    >
      <RangeForm
        first={
          <Field
            id="amount-min"
            label="Minimum (₹)"
            inputMode="decimal"
            autoComplete="off"
            placeholder="0"
            value={draft.min}
            aria-invalid={Boolean(error)}
            onChange={(e) => setDraft((d) => ({ ...d, min: e.target.value }))}
          />
        }
        second={
          <Field
            id="amount-max"
            label="Maximum (₹)"
            inputMode="decimal"
            autoComplete="off"
            placeholder="No limit"
            value={draft.max}
            aria-invalid={Boolean(error)}
            onChange={(e) => setDraft((d) => ({ ...d, max: e.target.value }))}
          />
        }
        error={error}
        onApply={apply}
        canClear={active}
        onClear={() => {
          onChange("", "");
          setOpen(false);
        }}
      />
    </RangePopover>
  );
}

function DateRangeFilter({
  from,
  to,
  onChange,
}: {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ from, to });
  const [error, setError] = useState<string | null>(null);
  const active = Boolean(from || to);

  const onOpenChange = (next: boolean) => {
    if (next) {
      setDraft({ from, to });
      setError(null);
    }
    setOpen(next);
  };

  const apply = () => {
    const nextFrom = parseIsoDate(draft.from);
    const nextTo = parseIsoDate(draft.to);
    if ((draft.from && !nextFrom) || (draft.to && !nextTo)) {
      setError("Enter complete dates.");
      return;
    }
    if (rangeProblems({ ...EMPTY_FILTERS, date_from: nextFrom, date_to: nextTo }).date) {
      setError("The start date is after the end date.");
      return;
    }
    onChange(nextFrom, nextTo);
    setOpen(false);
  };

  return (
    <RangePopover
      label="Incident date"
      summary={active ? dateRangeText(from, to) : "Any"}
      active={active}
      open={open}
      onOpenChange={onOpenChange}
    >
      <RangeForm
        first={
          <Field
            id="date-from"
            label="From"
            type="date"
            value={draft.from}
            max={draft.to || undefined}
            aria-invalid={Boolean(error)}
            onChange={(e) => setDraft((d) => ({ ...d, from: e.target.value }))}
          />
        }
        second={
          <Field
            id="date-to"
            label="To"
            type="date"
            value={draft.to}
            min={draft.from || undefined}
            aria-invalid={Boolean(error)}
            onChange={(e) => setDraft((d) => ({ ...d, to: e.target.value }))}
          />
        }
        error={error}
        onApply={apply}
        canClear={active}
        onClear={() => {
          onChange("", "");
          setOpen(false);
        }}
      />
    </RangePopover>
  );
}

export interface FilterChip {
  key: string;
  label: string;
  value: string;
  /** The filters with this chip removed. */
  without: AlertFilters;
}

/** One chip per selected value, plus one per range, in filter-bar order. */
export function filterChips(filters: AlertFilters, providerNames: Map<string, string>): FilterChip[] {
  const chips: FilterChip[] = [];
  const keys = ["claim_type", "provider_id", "category", "severity", "amount_type", "status"] as const;
  for (const key of keys) {
    for (const value of filters[key]) {
      const label =
        key === "provider_id"
          ? (providerNames.get(value) ?? value)
          : (STATIC_OPTIONS[key].find((o) => o.value === value)?.label ?? value);
      chips.push({
        key: `${key}:${value}`,
        label: LIST_LABELS[key],
        value: label,
        without: { ...filters, [key]: (filters[key] as string[]).filter((v) => v !== value) },
      });
    }
  }
  if (filters.amount_min || filters.amount_max) {
    chips.push({
      key: "amount",
      label: "Amount",
      value: amountRangeText(filters.amount_min, filters.amount_max),
      without: { ...filters, amount_min: "", amount_max: "" },
    });
  }
  if (filters.date_from || filters.date_to) {
    chips.push({
      key: "date",
      label: "Incident date",
      value: dateRangeText(filters.date_from, filters.date_to),
      without: { ...filters, date_from: "", date_to: "" },
    });
  }
  return chips;
}

/** Removable chips for the filters in use (the dashboard shows these instead of the full bar). */
export function ActiveFilterChips({
  filters,
  onChange,
  actions,
}: {
  filters: AlertFilters;
  onChange: (next: AlertFilters) => void;
  actions?: React.ReactNode;
}) {
  const providerOptions = useProviderOptions();
  const chips = filterChips(filters, new Map(providerOptions.map((o) => [o.value, o.label])));
  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Active filters">
      <span className="text-[13px] font-medium text-muted-foreground">Filtered by</span>
      <ul className="contents">
        {chips.map((chip) => (
          <li
            key={chip.key}
            className="inline-flex h-7 max-w-full items-center gap-1 rounded-[min(var(--radius-md),10px)] border border-primary/40 bg-card pr-1 pl-2.5 text-[13px]"
          >
            <span className="shrink-0 text-muted-foreground">{chip.label}:</span>
            <span className="min-w-0 truncate font-medium">{chip.value}</span>
            <Button
              variant="ghost"
              size="icon-xs"
              className="ml-0.5 text-muted-foreground"
              aria-label={`Remove filter ${chip.label}: ${chip.value}`}
              onClick={() => onChange(chip.without)}
            >
              <X aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
      <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_FILTERS)}>
        <FilterX data-icon="inline-start" aria-hidden="true" />
        Clear all
      </Button>
      {actions}
    </div>
  );
}
