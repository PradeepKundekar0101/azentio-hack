import type { Metadata } from "next";

import { ReviewQueue } from "./review-queue";

export const metadata: Metadata = { title: "Review queue" };

export default function ReviewsPage() {
  return <ReviewQueue />;
}
