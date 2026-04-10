"use client";

import { AudioPlayerProvider } from "@/components/audio/AudioPlayerProvider";
import { GlobalPlayerBar } from "@/components/audio/GlobalPlayerBar";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <AudioPlayerProvider>
      <div className="min-h-screen pb-24">{children}</div>
      <GlobalPlayerBar />
    </AudioPlayerProvider>
  );
}
