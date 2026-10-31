import type { Metadata } from "next";

import { PageHeader } from "@/components/page";

import { DocumentList } from "./document-list";
import { UploadPanel } from "./upload-panel";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return (
    <>
      <PageHeader
        title="Documents"
        description="Invoices uploaded as PDFs or images, with the claim read from each one for review."
      />
      <div className="space-y-4">
        <UploadPanel />
        <DocumentList />
      </div>
    </>
  );
}
