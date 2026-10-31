import { FileSpreadsheet, LayoutDashboard, type LucideIcon, ReceiptText, ShieldAlert } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/alerts", label: "Alerts", icon: ShieldAlert },
  { href: "/imports", label: "Imports", icon: FileSpreadsheet },
  { href: "/documents", label: "Documents", icon: ReceiptText },
];

/** The nav section a path belongs to (`/alerts/123` -> Alerts). Home matches only itself. */
export function navItemForPath(pathname: string): NavItem | undefined {
  return NAV_ITEMS.find((item) =>
    item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
}
