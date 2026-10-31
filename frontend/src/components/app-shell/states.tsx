"use client";

import { RefreshCw, ServerCrash } from "lucide-react";

import { PRODUCT_NAME } from "@/components/brand";
import { Button } from "@/components/ui/button";

export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex justify-center py-20">
      <div className="flex max-w-sm flex-col items-center text-center" role="alert">
        <div className="mb-4 flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <ServerCrash className="size-5" aria-hidden="true" />
        </div>
        <h1 className="text-lg font-semibold">{PRODUCT_NAME} could not load</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">{message}</p>
        <Button variant="outline" className="mt-5" onClick={onRetry}>
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          Try again
        </Button>
      </div>
    </div>
  );
}
