"use client";

import { AudioPlayerProvider } from "@/components/audio/AudioPlayerProvider";
import { GlobalPlayerBar } from "@/components/audio/GlobalPlayerBar";
import { DevImpersonationBanner } from "@/components/DevImpersonationBanner";
import { OnboardingRouteGuard } from "@/components/OnboardingRouteGuard";
import { AuthProvider } from "@/context/AuthContext";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <DevImpersonationBanner />
      <AudioPlayerProvider>
        <OnboardingRouteGuard>
          <div className="min-h-screen pb-24">{children}</div>
        </OnboardingRouteGuard>
        <GlobalPlayerBar />
      </AudioPlayerProvider>
    </AuthProvider>
  );
}
