import type { Metadata } from "next";
import { Suspense } from "react";

import { ImportDetail, ImportDetailSkeleton } from "./import-detail";

export const metadata: Metadata = { title: "Import" };

export default function ImportPage({ params }: PageProps<"/imports/[id]">) {
  return (
    <Suspense fallback={<ImportDetailSkeleton />}>
      {params.then(({ id }) => (
        <ImportDetail id={id} />
      ))}
    </Suspense>
  );
}
