import { cn } from "@/lib/utils";
import { logoMark } from "@/styles/brand";

export const PRODUCT_NAME = "Claims Leakage";

/**
 * A drop leaking from a claim form: the product's one-line idea, at 24px. Drawn from the
 * geometry in src/styles/brand.ts in fixed brand colours, so the mark reads the same in both
 * themes, on the landing page and in the share images.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox={logoMark.viewBox} aria-hidden="true" className={cn("size-6 shrink-0", className)} fill="none">
      <rect width={logoMark.size} height={logoMark.size} rx={logoMark.radius} className="fill-brand-blue" />
      <path
        d={logoMark.form}
        className="stroke-brand-on-ink"
        strokeWidth={logoMark.strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d={logoMark.lines} className="stroke-brand-on-ink" strokeWidth={logoMark.strokeWidth} strokeLinecap="round" />
      <path d={logoMark.drop} className="fill-brand-on-ink" />
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
