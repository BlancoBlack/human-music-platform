"use client";

import { useRouter } from "next/navigation";
import { UploadWizardPageLayout } from "@/components/UploadWizardPageLayout";

export default function UserRegisterCompletePage() {
  const router = useRouter();

  return (
    <UploadWizardPageLayout className="max-w-2xl py-10">
      {/* EXPRESSION_LAYER: reserved for future illustration/motion integration */}
      <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        {"You're ready"}
      </h1>
      <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
        Your music profile is set. Start exploring your personalized feed.
      </p>
      <button
        type="button"
        onClick={() => {
          // onboarding completion must always lead to discovery
          router.replace("/discovery?from=onboarding");
        }}
        className="mt-8 w-full rounded-lg bg-[#F37D25] px-4 py-3 text-sm font-medium text-black hover:bg-[#F7A364]"
      >
        Discover music
      </button>
    </UploadWizardPageLayout>
  );
}
