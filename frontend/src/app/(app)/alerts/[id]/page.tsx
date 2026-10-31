import type { Metadata } from "next";
import { Suspense } from "react";

import { AlertDetailSkeleton, AlertDetailView } from "./alert-detail";

export const metadata: Metadata = { title: "Alert" };

export default function AlertPage({ params }: PageProps<"/alerts/[id]">) {
  return (
    <Suspense fallback={<AlertDetailSkeleton />}>
      {params.then(({ id }) => (
        <AlertDetailView id={id} />
      ))}
    </Suspense>
  );
}
