"use client";

import Link from "next/link";
import { Suspense } from "react";

import { Wordmark } from "@/components/brand";
import { Skeleton } from "@/components/ui/skeleton";
import { HOME_PATH } from "@/lib/auth/redirect";

import { SidebarNav } from "./sidebar-nav";
import { SystemStatus } from "./system-status";

/** Wordmark, navigation and backend status: the desktop sidebar and the mobile drawer. */
export function SidebarContents({
  onNavigate,
  headerAction,
}: {
  onNavigate?: () => void;
  headerAction?: React.ReactNode;
}) {
  return (
    <>
      {/* The transparent border matches the top bar's, so both centre on the same line. */}
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-transparent px-4">
        <Link
          href={HOME_PATH}
          onClick={onNavigate}
          className="-mx-1 flex rounded-md px-1 py-0.5 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
        >
          <Wordmark />
        </Link>
        {headerAction}
      </div>
      <div className="flex-1 overflow-y-auto px-2.5 pt-3">
        {/* usePathname suspends on dynamic routes that are not prerendered. */}
        <Suspense fallback={<NavSkeleton />}>
          <SidebarNav onNavigate={onNavigate} />
        </Suspense>
      </div>
      <div className="shrink-0 border-t border-sidebar-border px-2.5 py-3">
        <SystemStatus />
      </div>
    </>
  );
}

function NavSkeleton() {
  return (
    <div className="flex flex-col gap-0.5" aria-hidden="true">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="flex h-8 items-center gap-2.5 px-2.5">
          <Skeleton className="size-4 bg-sidebar-border" />
          <Skeleton className="h-3.5 w-20 bg-sidebar-border" />
        </div>
      ))}
    </div>
  );
}
