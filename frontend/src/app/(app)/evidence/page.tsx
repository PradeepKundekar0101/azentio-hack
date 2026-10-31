import type { Metadata } from "next";

import { EvidenceList } from "./evidence-list";

export const metadata: Metadata = { title: "Evidence" };

export default function EvidenceIndexPage() {
  return <EvidenceList />;
}
