import { redirect } from "next/navigation";

/** Legacy route; analytics UI lives at `/studio/analytics`. */
export default function LegacyArtistAnalyticsRedirectPage() {
  redirect("/studio/analytics");
}
