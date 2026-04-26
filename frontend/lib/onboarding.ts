import type { UserMe } from "@/lib/auth";

export type OnboardingRoute = "/onboarding";

export function resolveOnboardingRoute(user: UserMe | null): OnboardingRoute | null {
  if (!user) return null;
  const step = (user.onboarding_step || "").toUpperCase();
  if (step === "DISCOVERY_STARTED" || step === "COMPLETED") return null;
  if (step === "REGISTERED" || step === "PREFERENCES_SET") return "/onboarding";
  return null;
}

