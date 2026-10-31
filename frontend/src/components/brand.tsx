import { cn } from "@/lib/utils";
import { logoMark } from "@/styles/brand";

export const PRODUCT_NAME = "Claims Leakage";

/**
 * The logo tile: ledger lines with one block fallen out of the record (see
 * src/styles/brand.ts). Brand colours are fixed, so the mark looks the same in both themes.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox={logoMark.viewBox} aria-hidden="true" className={cn("size-6 shrink-0", className)}>
      <rect width={logoMark.size} height={logoMark.size} rx={logoMark.radius} className="fill-brand-blue" />
      <path d={logoMark.lines} className="fill-brand-on-ink" />
      <path d={logoMark.leak} className="fill-brand-signal" />
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
