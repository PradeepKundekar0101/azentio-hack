import {
  Inbox,
  FileSpreadsheet,
  LayoutDashboard,
  type LucideIcon,
  ReceiptText,
  ScrollText,
  ShieldAlert,
  UsersRound,
  Wallet,
} from "lucide-react";

import type { Role } from "@/lib/auth/permissions";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown only to these roles; the API refuses everyone else anyway. */
  roles?: readonly Role[];
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/claims", label: "Claims", icon: Wallet },
  { href: "/alerts", label: "Alerts", icon: ShieldAlert },
  { href: "/reviews", label: "Review queue", icon: Inbox },
  { href: "/evidence", label: "Evidence", icon: ScrollText },
  { href: "/imports", label: "Imports", icon: FileSpreadsheet },
  { href: "/documents", label: "Documents", icon: ReceiptText },
  { href: "/users", label: "Users", icon: UsersRound, roles: ["admin"] },
];

/** The nav items a role may open. An unknown (still loading) role sees only the shared items. */
export function navItemsFor(role: Role | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || (role !== undefined && item.roles.includes(role)));
}

/** Pages reached from a section that live outside its path. */
const SECTION_ALIASES: Record<string, string> = {};

/** The nav section a path belongs to (`/alerts/123` -> Alerts). Home matches only itself. */
export function navItemForPath(pathname: string): NavItem | undefined {
  for (const [prefix, section] of Object.entries(SECTION_ALIASES)) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) pathname = section;
  }
  return NAV_ITEMS.find((item) =>
    item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
}
