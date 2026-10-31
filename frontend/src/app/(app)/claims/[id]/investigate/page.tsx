import type { Metadata } from "next";
import { Suspense } from "react";

import { InvestigationView, InvestigationSkeleton } from "./investigation";

export const metadata: Metadata = { title: "Investigate claim" };

export default function InvestigatePage({ params }: PageProps<"/claims/[id]/investigate">) {
  return (
    <Suspense fallback={<InvestigationSkeleton />}>
      {params.then(({ id }) => (
        <InvestigationView id={decodeURIComponent(id)} />
      ))}
    </Suspense>
  );
}
