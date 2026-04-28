import { GlobalNavbar } from "@/components/navigation/GlobalNavbar";
import { StudioSecondaryNavbar } from "@/components/studio/StudioSecondaryNavbar";

export function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <GlobalNavbar />
      <StudioSecondaryNavbar />
      <main className="mx-auto w-full max-w-7xl px-4 py-8">{children}</main>
    </div>
  );
}
