import type { Metadata } from "next";
import { Suspense } from "react";

import { EvidenceSkeleton, EvidenceView } from "./evidence-view";

export const metadata: Metadata = { title: "Evidence trail" };

export default function EvidencePage({ params }: PageProps<"/claims/[id]/evidence">) {
  return (
    <Suspense fallback={<EvidenceSkeleton />}>
      {params.then(({ id }) => (
        <EvidenceView id={id} />
      ))}
    </Suspense>
  );
}
