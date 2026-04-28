import type { UserMe } from "@/lib/auth";

/**
 * Centralized creator-role predicate for navigation and route affordances.
 * Handles current role model and sub-role expansion safely.
 */
export function isCreator(user: UserMe | null | undefined): boolean {
  if (!user) return false;
  const subRole = String(user.sub_role || "")
    .trim()
    .toLowerCase();
  if (subRole === "artist" || subRole === "label") {
    return true;
  }
  const roles = Array.isArray(user.roles) ? user.roles : [];
  return roles.some((role) => {
    const normalized = String(role || "")
      .trim()
      .toLowerCase();
    return normalized === "artist" || normalized === "label";
  });
}
