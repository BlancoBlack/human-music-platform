import { AuthGuard } from "@/components/AuthGuard";
import { StudioLayout } from "@/components/studio/StudioLayout";

export default function StudioRouteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <StudioLayout>{children}</StudioLayout>
    </AuthGuard>
  );
}
