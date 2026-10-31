import { FileUp } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { FormatList } from "@/components/format-list";
import { PageHeader } from "@/components/page";

import { ReferenceData } from "./reference-data";

export const metadata: Metadata = { title: "Imports" };

export default function ImportsPage() {
  return (
    <>
      <PageHeader
        title="Imports"
        description="Upload claims data as CSV, Excel or JSON and see how every row was handled."
      />
      <div className="space-y-4">
        <EmptyState
          icon={FileUp}
          title="No imports yet"
          description="Upload claims, line items, policies, policy rules and settlements. Every row ends up accepted, accepted with warnings, or rejected with a reason."
        >
          <FormatList label="Accepted formats" formats={["CSV", "Excel", "JSON"]} note="File upload is not available yet." />
        </EmptyState>
        <ReferenceData />
      </div>
    </>
  );
}
