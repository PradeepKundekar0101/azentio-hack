import type { Metadata } from "next";
import { Suspense } from "react";

import { ClaimDetailSkeleton, ClaimDetailView } from "./claim-detail";

export const metadata: Metadata = { title: "Claim" };

export default function ClaimPage({ params }: PageProps<"/claims/[id]">) {
  return (
    <Suspense fallback={<ClaimDetailSkeleton />}>
      {params.then(({ id }) => (
        <ClaimDetailView id={id} />
      ))}
    </Suspense>
  );
}
