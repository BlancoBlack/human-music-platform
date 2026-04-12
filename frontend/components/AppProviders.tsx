"use client";

import { AudioPlayerProvider } from "@/components/audio/AudioPlayerProvider";
import { GlobalPlayerBar } from "@/components/audio/GlobalPlayerBar";
import { AuthProvider } from "@/context/AuthContext";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AudioPlayerProvider>
        <div className="min-h-screen pb-24">{children}</div>
        <GlobalPlayerBar />
      </AudioPlayerProvider>
    </AuthProvider>
  );
}
