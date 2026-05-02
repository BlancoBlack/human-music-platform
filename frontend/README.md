This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

### Global player (listening ingestion)

The app wraps all pages in `AudioPlayerProvider` (see `components/AppProviders.tsx`). Playback uses `NEXT_PUBLIC_API_BASE` (defaults to `http://localhost:8000`; set in `.env.local` — see `.env.example`).

`lib/listening.ts` sends **`X-User-Id`** (from **`NEXT_PUBLIC_LISTENING_USER_ID`**, default `1`) on **`/stream/*`** calls. The API accepts that header **only** when **`ENABLE_LEGACY_AUTH=true`** on the backend; **the default is `false`**, so those calls **must use a Bearer access JWT** instead (same as the rest of the app) or you must temporarily enable legacy auth for local experiments.

For auth cookies and CORS, run the Next dev server at **http://localhost:3000** and point `NEXT_PUBLIC_API_BASE` at **http://localhost:8000** (not `127.0.0.1`).

### Drag & Drop (Playlists)

Playlist tracks can be reordered with drag and drop on the playlist detail page (**`/library/playlists/[id]`**). Only the **playlist owner** sees the reorder handle. The UI uses **@dnd-kit** (core + sortable; handle-based interaction). Dependencies are installed with **`npm install`** in this directory — see the repo root **README** → **Frontend setup**.

### Dev-only impersonation (debugging)

Backend must have **`APP_ENV=development`** (or `dev`) **and** **`ENABLE_DEV_IMPERSONATION=true`**. Log in as yourself, then from any client code (e.g. React DevTools on a component that uses `useAuth()`):

`await impersonateUser(<targetUserId>)`

A banner shows the target and actor; **Exit impersonation** calls `refreshSession()` to restore the normal access token from the httpOnly refresh cookie. No refresh token is issued for impersonation.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
