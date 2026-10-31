"use client";

import { LogOut, Menu, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getErrorMessage } from "@/lib/api/errors";
import { useLogout, useMe } from "@/lib/auth/hooks";
import { HOME_PATH, LOGIN_PATH } from "@/lib/auth/redirect";

import { SidebarContents } from "./sidebar";

/** Sticky header: the mobile menu and wordmark, then the user, theme toggle and sign-out. */
export function TopBar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { data: user } = useMe();
  const logout = useLogout();

  // A full page load after signing out drops every cached query and route, so nothing
  // from the session survives in memory.
  const signOut = () =>
    logout.mutate(undefined, {
      onSuccess: () => window.location.replace(LOGIN_PATH),
      onError: (error) => toast.error(getErrorMessage(error)),
    });

  return (
    <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b bg-canvas/90 px-4 backdrop-blur-sm supports-backdrop-filter:bg-canvas/75 sm:px-6 2xl:px-8">
      <Button
        variant="ghost"
        size="icon"
        className="-ml-2 lg:hidden"
        aria-label="Open navigation"
        onClick={() => setMenuOpen(true)}
      >
        <Menu aria-hidden="true" />
      </Button>
      <Link
        href={HOME_PATH}
        className="flex min-w-0 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
      >
        <Wordmark />
      </Link>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" showCloseButton={false} className="gap-0 bg-sidebar p-0 data-[side=left]:w-64">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">Sections of the app</SheetDescription>
          <div className="flex h-full flex-col">
            <SidebarContents
              onNavigate={() => setMenuOpen(false)}
              headerAction={
                <SheetClose asChild>
                  <Button variant="ghost" size="icon-sm" className="-mr-1.5" aria-label="Close navigation">
                    <X aria-hidden="true" />
                  </Button>
                </SheetClose>
              }
            />
          </div>
        </SheetContent>
      </Sheet>

      <div className="ml-auto flex min-w-0 items-center gap-1">
        <div className="mr-2 flex min-w-0 items-center">
          {user ? <UserBadge username={user.username} /> : <UserBadgeSkeleton />}
        </div>
        <ThemeToggle />
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Sign out"
              onClick={signOut}
              disabled={!user || logout.isPending || logout.isSuccess}
            >
              <LogOut aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Sign out</TooltipContent>
        </Tooltip>
      </div>
    </header>
  );
}

/** Initial and username; on phones only the initial shows and the name is for screen readers. */
function UserBadge({ username }: { username: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span
        aria-hidden="true"
        className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary uppercase ring-1 ring-primary/15 ring-inset"
      >
        {username.slice(0, 1)}
      </span>
      <span className="sr-only truncate text-sm font-medium sm:not-sr-only">
        <span className="sr-only">Signed in as </span>
        {username}
      </span>
    </span>
  );
}

function UserBadgeSkeleton() {
  return (
    <span className="flex items-center gap-2" aria-hidden="true">
      <Skeleton className="size-6 rounded-full" />
      <Skeleton className="hidden h-3.5 w-14 sm:block" />
    </span>
  );
}
