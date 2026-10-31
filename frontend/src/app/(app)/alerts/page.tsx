import { ArrowRight, ShieldAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Alerts" };

export default function AlertsPage() {
  return (
    <>
      <PageHeader
        title="Alerts"
        description="Every detected issue with the rule behind it, its amount and the records that support it."
      />
      <EmptyState
        icon={ShieldAlert}
        title="No alerts yet"
        description="Alerts are raised when a processed claim breaks a policy rule or duplicates an earlier claim. Import claims data to get started."
        actions={
          <Button asChild>
            <Link href="/imports">
              Go to Imports
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
        }
      />
    </>
  );
}
