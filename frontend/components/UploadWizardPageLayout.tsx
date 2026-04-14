import type { ElementType, ReactNode } from "react";

/** Centered max-width + horizontal padding (shared by upload wizard and album flow). */
export const UPLOAD_WIZARD_PAGE_SHELL_CLASS = "mx-auto max-w-2xl px-4";

/** Default vertical padding for full-page upload steps (matches UploadWizard). */
export const UPLOAD_WIZARD_PAGE_LAYOUT_CLASS = `${UPLOAD_WIZARD_PAGE_SHELL_CLASS} py-10`;

type UploadWizardPageLayoutProps = {
  children: ReactNode;
  /** Merged after the canonical layout class (e.g. `min-h-screen`). */
  className?: string;
  as?: "main" | "div";
};

/**
 * Canonical page shell for single-song upload and album sub-flows.
 * Keeps max-width, horizontal centering, and padding aligned with UploadWizard.
 */
export function UploadWizardPageLayout({
  children,
  className,
  as = "main",
}: UploadWizardPageLayoutProps) {
  const Comp = as as ElementType;
  const merged = className
    ? `${UPLOAD_WIZARD_PAGE_LAYOUT_CLASS} ${className}`
    : UPLOAD_WIZARD_PAGE_LAYOUT_CLASS;
  return <Comp className={merged}>{children}</Comp>;
}
