"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export function AuthSessionBar() {
  const router = useRouter();
  const { isAuthenticated, logout, initializing } = useAuth();

  if (initializing || !isAuthenticated) {
    return null;
  }

  return (
    <div className="flex justify-end border-b border-neutral-200 px-4 py-2 dark:border-neutral-800">
      <button
        type="button"
        onClick={async () => {
          await logout();
          router.push("/login");
        }}
        className="text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
      >
        Logout
      </button>
    </div>
  );
}
