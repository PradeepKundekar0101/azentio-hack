"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { getErrorMessage } from "@/lib/api/errors";
import { useMe } from "@/lib/auth/hooks";
import { loginPath } from "@/lib/auth/redirect";

import { SidebarContents } from "./sidebar";
import { LoadError } from "./states";
import { TopBar } from "./top-bar";

/**
 * Authenticated chrome: sidebar, top bar and the client-side session guard.
 *
 * The frame and the page render immediately (so navigations are instant and the static
 * shell is prerendered); only the user-dependent parts wait for /auth/me. The proxy has
 * already redirected requests without a session cookie, so the remaining case is an
 * expired cookie, which SessionGate handles.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="canvas-glow min-h-dvh bg-canvas">
      {/* First in the tab order, ahead of the sidebar links. */}
      <a
        href="#main"
        className="sr-only rounded-md border bg-card text-sm font-medium shadow-sm outline-none focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1.5 focus-visible:ring-2 focus-visible:ring-ring"
      >
        Skip to content
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <SidebarContents />
      </aside>
      <div className="lg:pl-56">
        <TopBar />
        <main id="main" tabIndex={-1} className="page-enter px-4 py-5 outline-none sm:px-6 lg:py-6 2xl:px-8">
          <Suspense fallback={<ContentSkeleton />}>
            <SessionGate>{children}</SessionGate>
          </Suspense>
        </main>
      </div>
    </div>
  );
}

/** Renders the page, or sends the user to /login once the backend says the session ended. */
function SessionGate({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const router = useRouter();

  const signedOut = me.isSuccess && me.data === null;
  useEffect(() => {
    if (!signedOut) return;
    const { pathname, search } = window.location;
    router.replace(loginPath(`${pathname}${search}`));
  }, [signedOut, router]);

  if (me.isError) return <LoadError message={getErrorMessage(me.error)} onRetry={() => me.refetch()} />;
  if (signedOut) return <ContentSkeleton />;
  return children;
}

function ContentSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-7 w-48" />
      <Skeleton className="h-4 w-80 max-w-full" />
      <Skeleton className="mt-4 h-64 w-full" />
    </div>
  );
}
