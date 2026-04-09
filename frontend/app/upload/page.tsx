"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { UploadWizard } from "@/components/UploadWizard";

function UploadPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawArtistId = searchParams.get("artist_id");
  const shouldRedirect =
    rawArtistId != null && rawArtistId.trim().length > 0;

  useEffect(() => {
    if (!shouldRedirect) return;
    const q = searchParams.toString();
    router.replace(q ? `/artist-upload?${q}` : "/artist-upload");
  }, [shouldRedirect, router, searchParams]);

  if (shouldRedirect) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <p className="text-sm text-neutral-500">Redirecting…</p>
      </main>
    );
  }

  return <UploadWizard basePath="/upload" />;
}

export default function UploadPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-2xl px-4 py-10">
          <p className="text-sm text-neutral-500">Loading…</p>
        </main>
      }
    >
      <UploadPageInner />
    </Suspense>
  );
}
