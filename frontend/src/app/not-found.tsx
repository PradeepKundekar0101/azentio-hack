import { SearchX } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Wordmark } from "@/components/brand";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas px-4 py-6 sm:px-6">
      <header className="flex h-8 items-center">
        <Wordmark />
      </header>
      <main className="flex flex-1 items-start justify-center pt-[clamp(2.5rem,14vh,8rem)] pb-10">
        <div className="flex max-w-sm flex-col items-center text-center">
          <div className="flex size-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <SearchX className="size-5" aria-hidden="true" />
          </div>
          <h1 className="mt-4 text-lg font-semibold">Page not found</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            The address may be mistyped, or the page may have moved.
          </p>
          <Button asChild variant="outline" className="mt-5">
            <Link href="/">Go to Dashboard</Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
