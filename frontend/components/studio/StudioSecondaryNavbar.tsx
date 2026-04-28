"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { isCreator } from "@/lib/identity";

const ITEMS: { href: string; label: string }[] = [
  { href: "/studio/catalog", label: "Catalog" },
  { href: "/studio/analytics", label: "Analytics" },
  { href: "/studio/payouts", label: "Payouts" },
  { href: "/upload", label: "Upload" },
];

function isActive(pathname: string, href: string): boolean {
  if (pathname === href) return true;
  return pathname.startsWith(`${href}/`);
}

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function StudioSecondaryNavbar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const creatorMode = isCreator(user);

  const displayName = String(user?.display_name || "").trim();
  const email = String(user?.email || "").trim();
  const emailPrefix = email ? email.split("@")[0] : "";
  const rawName = creatorMode
    ? displayName || emailPrefix || "My Studio"
    : "My Studio";
  const artistName = capitalize(rawName);

  return (
    <nav aria-label="Studio navigation">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-sm">
        <Link
          href="/studio"
          className={
            pathname === "/studio"
              ? "font-semibold text-neutral-900 dark:text-neutral-100"
              : "font-medium text-neutral-700 hover:text-neutral-900 dark:text-neutral-300 dark:hover:text-neutral-100"
          }
        >
          {artistName}
        </Link>
        {ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={
              isActive(pathname, item.href)
                ? "font-semibold text-neutral-900 dark:text-neutral-100"
                : "font-medium text-neutral-700 hover:text-neutral-900 dark:text-neutral-300 dark:hover:text-neutral-100"
            }
          >
            {item.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
