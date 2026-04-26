"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { UploadWizardPageLayout } from "@/components/UploadWizardPageLayout";
import { resolveOnboardingRoute } from "@/lib/onboarding";

type RegisterMode = "choice" | "user" | "artist";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [mode, setMode] = useState<RegisterMode>("choice");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [username, setUsername] = useState("");
  const [artistName, setArtistName] = useState("");
  const [subRole, setSubRole] = useState<"artist" | "label">("artist");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitAttempted(true);
    setError(null);
    if (password.length < 8) {
      return;
    }
    setPending(true);
    try {
      const payload =
        mode === "artist"
          ? {
              email,
              password,
              username: artistName,
              artist_name: artistName,
              role: "artist" as const,
              sub_role: subRole,
            }
          : {
              email,
              password,
              username,
              role: "user" as const,
            };
      const user = await register(payload);
      router.replace(resolveOnboardingRoute(user) ?? "/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setPending(false);
    }
  }

  if (mode === "choice") {
    return (
      <UploadWizardPageLayout className="py-16">
        <h1 className="text-3xl font-semibold text-neutral-900 dark:text-neutral-100">
          Create it or Feel it. Choose your side.
        </h1>
        <div className="mt-8 flex flex-col items-center justify-center gap-4 md:flex-row md:gap-6">
          <button
            type="button"
            onClick={() => setMode("user")}
            className="w-full max-w-xs rounded-xl bg-[#F37D25] px-8 py-3 text-center text-sm font-medium text-black transition-colors hover:bg-[#F7A364] md:w-auto"
          >
            I enjoy music
          </button>
          <button
            type="button"
            onClick={() => setMode("artist")}
            className="w-full max-w-xs rounded-xl bg-neutral-100 px-8 py-3 text-center text-sm font-medium text-neutral-900 transition-colors hover:bg-neutral-200 dark:bg-neutral-800 dark:text-neutral-100 dark:hover:bg-neutral-700 md:w-auto"
          >
            I make music
          </button>
        </div>
        <p className="mt-6 text-sm text-neutral-600 dark:text-neutral-400">
          Already have an account?{" "}
          <Link href="/login" className="font-medium underline">
            Sign in
          </Link>
        </p>
      </UploadWizardPageLayout>
    );
  }

  return (
    <UploadWizardPageLayout className="max-w-md py-16">
      <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        {mode === "user" ? "Start listening in seconds" : "Start uploading music in seconds"}
      </h1>
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <div>
          <label
            htmlFor="email"
            className="block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-neutral-900 shadow-sm dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-100"
          />
        </div>
        {mode !== "artist" ? (
          <div>
            <label
              htmlFor="username"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300"
            >
              Username
            </label>
            <input
              id="username"
              name="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-neutral-900 shadow-sm dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-100"
            />
          </div>
        ) : null}
        <div>
          <label
            htmlFor="password"
            className="block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            Password (min 8 characters)
          </label>
          <div className="relative mt-1">
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (!passwordTouched) setPasswordTouched(true);
              }}
              onBlur={() => setPasswordTouched(true)}
              aria-invalid={submitAttempted && password.length < 8}
              className={`w-full rounded-md border bg-white px-3 py-2 pr-12 text-neutral-900 shadow-sm transition-[border-color,box-shadow] duration-200 focus:outline-none focus:ring-2 dark:bg-neutral-900 dark:text-neutral-100 ${
                submitAttempted && password.length < 8
                  ? "border-red-500 focus:border-red-500 focus:ring-red-500/25 dark:border-red-400"
                  : password.length >= 8
                    ? "border-emerald-500/70 focus:border-emerald-500 focus:ring-emerald-500/25 dark:border-emerald-400/70"
                    : "border-neutral-300 focus:border-[#F37D25] focus:ring-[#F37D25]/25 dark:border-neutral-600"
              }`}
            />
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-2 top-1/2 inline-flex h-8 min-w-8 -translate-y-1/2 items-center justify-center rounded-md px-1 text-sm text-neutral-500 transition-colors hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
            >
              {showPassword ? "🙈" : "👁"}
            </button>
          </div>
          {submitAttempted && password.length < 8 ? (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400" role="alert">
              Minimum 8 characters
            </p>
          ) : passwordTouched && password.length > 0 && password.length < 8 ? (
            <p className="mt-1 text-xs text-red-500/85 dark:text-red-400/85">
              Minimum 8 characters
            </p>
          ) : password.length >= 8 ? (
            <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-400">
              Looks good
            </p>
          ) : null}
        </div>
        {mode === "artist" ? (
          <>
            <div>
              <label
                htmlFor="artistName"
                className="block text-sm font-medium text-neutral-700 dark:text-neutral-300"
              >
                {subRole === "label" ? "Label Name" : "Artist Name"}
              </label>
              <input
                id="artistName"
                name="artistName"
                required
                value={artistName}
                onChange={(e) => setArtistName(e.target.value)}
                placeholder={
                  subRole === "label"
                    ? "Enter your label name"
                    : "Enter your artist name"
                }
                className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-neutral-900 shadow-sm dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Account Type
              </label>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSubRole("artist")}
                  className={`rounded-md border px-3 py-2 text-sm ${subRole === "artist" ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900" : "border-neutral-300 dark:border-neutral-700"}`}
                >
                  Artist
                </button>
                <button
                  type="button"
                  onClick={() => setSubRole("label")}
                  className={`rounded-md border px-3 py-2 text-sm ${subRole === "label" ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900" : "border-neutral-300 dark:border-neutral-700"}`}
                >
                  Label
                </button>
              </div>
            </div>
          </>
        ) : null}
        {error ? (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-md bg-[#F37D25] px-4 py-2 text-sm font-medium text-black hover:bg-[#F7A364] disabled:opacity-50"
        >
          {pending
            ? "Creating account…"
            : mode === "artist"
              ? "Start uploading music in seconds"
              : "Start listening in seconds"}
        </button>
      </form>
    </UploadWizardPageLayout>
  );
}
