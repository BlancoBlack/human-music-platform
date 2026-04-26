"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { UploadWizardPageLayout } from "@/components/UploadWizardPageLayout";
import { submitOnboardingPreferences } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const GENRES = [
  "Hip-Hop",
  "Electronic",
  "R&B",
  "House",
  "Afrobeats",
  "Pop",
  "Rock",
  "Ambient",
  "Drill",
  "Latin",
];

export default function OnboardingPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [artistsInput, setArtistsInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canContinue = useMemo(() => selectedGenres.length > 0 && selectedGenres.length <= 5, [selectedGenres]);

  const toggleGenre = (genre: string) => {
    setSelectedGenres((prev) => {
      if (prev.includes(genre)) return prev.filter((g) => g !== genre);
      if (prev.length >= 5) return prev;
      return [...prev, genre];
    });
  };

  async function onContinue() {
    if (!canContinue) return;
    setPending(true);
    setError(null);
    try {
      const artists = artistsInput
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await submitOnboardingPreferences({ genres: selectedGenres, artists });
      await refreshUser();
      // onboarding completion must always lead to discovery (via completion milestone page)
      router.replace("/user-register-complete");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not continue onboarding");
    } finally {
      setPending(false);
    }
  }

  return (
    <UploadWizardPageLayout className="max-w-2xl py-10">
      <h1 className="text-2xl font-semibold">Your taste, fast</h1>
      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">Pick up to 5 genres.</p>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {GENRES.map((genre) => {
          const selected = selectedGenres.includes(genre);
          return (
            <button
              key={genre}
              type="button"
              onClick={() => toggleGenre(genre)}
              className={`rounded-lg border px-3 py-3 text-sm ${selected ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900" : "border-neutral-300 dark:border-neutral-700"}`}
            >
              {genre}
            </button>
          );
        })}
      </div>
      <label className="mt-6 block">
        <span className="text-sm text-neutral-700 dark:text-neutral-300">Optional artists (comma-separated)</span>
        <input
          value={artistsInput}
          onChange={(e) => setArtistsInput(e.target.value)}
          placeholder="e.g. Kaytranada, Little Simz"
          className="mt-2 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-900"
        />
      </label>
      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      <button
        type="button"
        disabled={!canContinue || pending}
        onClick={onContinue}
        className="mt-6 w-full rounded-lg bg-[#F37D25] px-4 py-3 text-sm font-medium text-black hover:bg-[#F7A364] disabled:opacity-50"
      >
        {pending ? "Preparing your feed..." : "Discover music"}
      </button>
    </UploadWizardPageLayout>
  );
}
