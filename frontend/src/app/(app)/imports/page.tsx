import type { Metadata } from "next";

import { PageHeader } from "@/components/page";

import { ImportHistory } from "./import-history";
import { ReferenceData } from "./reference-data";
import { UploadPanel } from "./upload-panel";

export const metadata: Metadata = { title: "Imports" };

export default function ImportsPage() {
  return (
    <>
      <PageHeader
        title="Imports"
        description="Upload claims data as CSV, Excel or JSON and see how every row was handled."
      />
      <div className="space-y-4">
        <UploadPanel />
        <ImportHistory />
        <ReferenceData />
      </div>
    </>
  );
}
