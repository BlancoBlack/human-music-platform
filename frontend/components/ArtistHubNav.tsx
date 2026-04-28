"use client";

type ArtistHubNavProps = {
  artistId: number;
  active: "overview" | "analytics" | "payouts" | "catalog" | "upload";
};

/**
 * Legacy artist-hub nav is intentionally disabled.
 * Navigation source of truth lives in GlobalNavbar + StudioSecondaryNavbar.
 */
export function ArtistHubNav({ artistId, active }: ArtistHubNavProps) {
  void artistId;
  void active;
  return null;
}
