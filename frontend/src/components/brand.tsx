import { cn } from "@/lib/utils";

export const PRODUCT_NAME = "Claims Leakage";

/** A drop leaking from a claim form: the product's one-line idea, at 24px. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn("size-6 shrink-0", className)} fill="none">
      <rect width="24" height="24" rx="5" className="fill-primary" />
      <path
        d="M7.5 5.5h6l3 3v5.25M7.5 5.5v13h4.75"
        className="stroke-primary-foreground"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M10 9.75h3M10 12.5h2.5" className="stroke-primary-foreground" strokeWidth="1.6" strokeLinecap="round" />
      <path
        d="M16.25 14.25c1.2 1.45 1.95 2.5 1.95 3.4a1.95 1.95 0 0 1-3.9 0c0-.9.75-1.95 1.95-3.4z"
        className="fill-primary-foreground"
      />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-[-0.01em] whitespace-nowrap text-foreground">
        {PRODUCT_NAME}
      </span>
    </span>
  );
}
