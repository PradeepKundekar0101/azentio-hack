"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useMe } from "@/lib/auth/hooks";
import { cn } from "@/lib/utils";

import { navItemForPath, navItemsFor } from "./nav";

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = navItemForPath(pathname);
  const { data: user } = useMe();
  const items = navItemsFor(user?.role);

  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {items.map((item) => {
        const isActive = active?.href === item.href;
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "group relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13.5px] font-medium outline-none",
              "text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground",
              "focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:ring-offset-1 focus-visible:ring-offset-sidebar",
              isActive &&
                "bg-sidebar-accent text-sidebar-accent-foreground shadow-[0_0_0_1px_var(--sidebar-border)] hover:bg-sidebar-accent",
            )}
          >
            {isActive && (
              <span
                aria-hidden="true"
                className="absolute inset-y-1.5 left-0 w-[3px] rounded-r-full bg-sidebar-primary"
              />
            )}
            <Icon
              aria-hidden="true"
              className={cn(
                "size-4 shrink-0 text-sidebar-foreground/60 group-hover:text-sidebar-accent-foreground",
                isActive && "text-sidebar-primary group-hover:text-sidebar-primary",
              )}
              strokeWidth={2}
            />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
