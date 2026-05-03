"use client";

import { AudioPlayerProvider } from "@/components/audio/AudioPlayerProvider";
import { GlobalPlayerBar } from "@/components/audio/GlobalPlayerBar";
import { DevImpersonationBanner } from "@/components/DevImpersonationBanner";
import { OnboardingRouteGuard } from "@/components/OnboardingRouteGuard";
import { QueryProvider } from "@/components/QueryProvider";
import { AuthProvider } from "@/context/AuthContext";
import { AuthPromptProvider } from "@/context/AuthPromptContext";
import { ToastProvider } from "@/context/ToastContext";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        <QueryProvider>
          <AuthPromptProvider>
            <DevImpersonationBanner />
            <AudioPlayerProvider>
              <OnboardingRouteGuard>
                <div className="min-h-screen pb-24">{children}</div>
              </OnboardingRouteGuard>
              <GlobalPlayerBar />
            </AudioPlayerProvider>
          </AuthPromptProvider>
        </QueryProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
