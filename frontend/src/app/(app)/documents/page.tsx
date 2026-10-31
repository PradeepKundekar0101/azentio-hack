import { ArrowRight, ScanText } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { FormatList } from "@/components/format-list";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return (
    <>
      <PageHeader
        title="Documents"
        description="Invoices uploaded as PDFs or images, with the claim read from each one for review."
      />
      <EmptyState
        icon={ScanText}
        title="No documents yet"
        description="Upload an invoice PDF or scan to have its claim and line items extracted for review. Claims are checked against imported policies."
        actions={
          <Button asChild variant="outline">
            <Link href="/imports">
              Start with an import
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
        }
      >
        <FormatList label="Accepted formats" formats={["PDF", "PNG", "JPEG"]} note="Up to 15 MB each. Upload is not available yet." />
      </EmptyState>
    </>
  );
}
