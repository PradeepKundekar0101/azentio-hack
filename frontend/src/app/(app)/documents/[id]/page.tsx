import type { Metadata } from "next";
import { Suspense } from "react";

import { DocumentReview, DocumentReviewSkeleton } from "./document-review";

export const metadata: Metadata = { title: "Review document" };

export default function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  return (
    <Suspense fallback={<DocumentReviewSkeleton />}>
      {params.then(({ id }) => (
        <DocumentReview id={id} />
      ))}
    </Suspense>
  );
}
