import { StudioLayout } from "@/components/studio/StudioLayout";

export default function StudioRouteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <StudioLayout>{children}</StudioLayout>;
}
