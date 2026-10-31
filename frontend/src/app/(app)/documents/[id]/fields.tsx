"use client";

import { CircleAlert } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export interface FieldMeta {
  /** id of the control; the label, hint and error ids derive from it. */
  id: string;
  label: string;
  error?: string;
  /** Shown when there is no error. */
  hint?: React.ReactNode;
  /** Empty and needed: hints that the invoice did not have it. */
  missing?: boolean;
  optional?: boolean;
  className?: string;
}

/** aria props tying a control to its hint or error. */
export function controlProps({ id, error, hint, missing }: Pick<FieldMeta, "id" | "error" | "hint" | "missing">) {
  const described = error ? `${id}-error` : hint || missing ? `${id}-hint` : undefined;
  return {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": described,
  } as const;
}

export function Field({ id, label, error, hint, missing, optional, className, children }: FieldMeta & { children: React.ReactNode }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <Label htmlFor={id} className="gap-1.5 text-[13px] leading-4">
        {label}
        {optional && <span className="text-xs font-normal text-muted-foreground">Optional</span>}
      </Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="flex items-start gap-1 text-xs leading-4 text-destructive">
          <CircleAlert className="mt-px size-3 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{error}</span>
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs leading-4 text-muted-foreground">
          {hint}
        </p>
      ) : missing ? (
        <p id={`${id}-hint`} className="text-xs leading-4 text-warning">
          Not found on the invoice
        </p>
      ) : null}
    </div>
  );
}

export function TextField({
  value,
  onChange,
  type = "text",
  inputMode,
  placeholder,
  prefix,
  inputClassName,
  ...meta
}: FieldMeta & {
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "date";
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
  placeholder?: string;
  /** A unit shown inside the input, e.g. "₹". */
  prefix?: string;
  inputClassName?: string;
}) {
  const input = (
    <Input
      {...controlProps(meta)}
      type={type}
      inputMode={inputMode}
      placeholder={placeholder}
      value={value}
      autoComplete="off"
      spellCheck={false}
      onChange={(event) => onChange(event.currentTarget.value)}
      className={cn("bg-card", type === "date" && "min-w-0 [&::-webkit-date-and-time-value]:text-left", prefix && "pl-6", inputClassName)}
    />
  );
  return (
    <Field {...meta}>
      {prefix ? (
        <div className="relative">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-sm text-muted-foreground"
          >
            {prefix}
          </span>
          {input}
        </div>
      ) : (
        input
      )}
    </Field>
  );
}

export function SelectField({
  value,
  onChange,
  placeholder,
  options,
  children,
  ...meta
}: FieldMeta & {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  options?: readonly { value: string; label: string }[];
  /** Custom items (e.g. grouped) in place of `options`. */
  children?: React.ReactNode;
}) {
  return (
    <Field {...meta}>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger {...controlProps(meta)} className="w-full min-w-0 bg-card">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent position="popper" align="start" className="max-h-80">
          {children ??
            options?.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
        </SelectContent>
      </Select>
    </Field>
  );
}
