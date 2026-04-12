"use client";

import { AudioPlayerProvider } from "@/components/audio/AudioPlayerProvider";
import { GlobalPlayerBar } from "@/components/audio/GlobalPlayerBar";
import { AuthSessionBar } from "@/components/AuthSessionBar";
import { DevImpersonationBanner } from "@/components/DevImpersonationBanner";
import { AuthProvider } from "@/context/AuthContext";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthSessionBar />
      <DevImpersonationBanner />
      <AudioPlayerProvider>
        <div className="min-h-screen pb-24">{children}</div>
        <GlobalPlayerBar />
      </AudioPlayerProvider>
    </AuthProvider>
  );
}
