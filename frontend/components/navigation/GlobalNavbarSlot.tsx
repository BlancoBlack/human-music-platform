"use client";

import { usePathname } from "next/navigation";
import { GlobalNavbar } from "@/components/navigation/GlobalNavbar";

export function GlobalNavbarSlot() {
  const pathname = usePathname();
  if (pathname.startsWith("/studio") || pathname === "/upload") {
    return null;
  }
  return <GlobalNavbar />;
}
