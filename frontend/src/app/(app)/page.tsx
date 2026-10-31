import { ArrowRight, ChartColumn } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Leakage across processed claims, with calculated and estimated amounts kept apart."
      />
      <EmptyState
        icon={ChartColumn}
        title="No claims processed yet"
        description="Import claims data and run validation. Key figures, leakage by category and the providers with the most leakage appear here."
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
