import Link from "next/link";

export default function StudioReleaseEditPlaceholderPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Edit Release</h1>
      <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-400">
        Release editor entry point for release #{params.id}. Full editing tools will be added here.
      </p>
      <p className="mt-6 text-sm">
        <Link href="/studio/catalog" className="text-neutral-900 hover:underline dark:text-white">
          Back to catalog
        </Link>
      </p>
    </main>
  );
}
