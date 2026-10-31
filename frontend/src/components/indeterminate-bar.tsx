import { cn } from "@/lib/utils";

/** Progress with no known end: a segment sliding across its track. */
export function IndeterminateBar({ label, className }: { label: string; className?: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      className={cn("relative h-1 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <div className="absolute inset-y-0 left-0 w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-primary motion-reduce:w-full motion-reduce:animate-pulse" />
    </div>
  );
}
