import { AMOUNT_TYPE_DEFINITIONS, AMOUNT_TYPES } from "@/lib/alerts/model";
import { cn } from "@/lib/utils";

import { AmountTypeBadge } from "./badges";

/** The three amount types and what each means, shown wherever amounts are listed. */
export function AmountTypeLegend({ className }: { className?: string }) {
  return (
    <section
      aria-labelledby="amount-legend-title"
      className={cn("rounded-xl border border-dashed border-border px-4 py-3", className)}
    >
      <h2 id="amount-legend-title" className="text-xs font-semibold text-muted-foreground">
        Amount types
      </h2>
      <dl className="mt-2 grid gap-x-6 gap-y-2.5 md:grid-cols-3">
        {AMOUNT_TYPES.map((type) => (
          <div key={type} className="flex flex-col items-start gap-1">
            <dt>
              <AmountTypeBadge type={type} />
            </dt>
            <dd className="text-[13px] leading-5 text-pretty text-muted-foreground">{AMOUNT_TYPE_DEFINITIONS[type]}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
