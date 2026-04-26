"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function Home() {
  const [balance, setBalance] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const fetchBalance = () => {
    apiFetch("/balance")
      .then((res) => res.json())
      .then((data) => setBalance(data));
  };

  useEffect(() => {
    fetchBalance();
  }, []);

  const handleStream = async () => {
    setLoading(true);

    await apiFetch("/stream", {
      method: "POST",
    });

    // actualizar balance después del stream
    fetchBalance();

    setLoading(false);
  };

  return (
    <main className="p-10">
      <div className="mb-6 flex flex-wrap gap-4">
        <Link
          href="/upload"
          className="text-sm font-medium text-neutral-600 underline-offset-4 hover:underline dark:text-neutral-400"
        >
          Upload song
        </Link>
        <Link
          href="/login"
          className="text-sm font-medium text-neutral-600 underline-offset-4 hover:underline dark:text-neutral-400"
        >
          Sign in
        </Link>
        <Link
          href="/register"
          className="text-sm font-medium text-neutral-600 underline-offset-4 hover:underline dark:text-neutral-400"
        >
          Register
        </Link>
      </div>
      <h1 className="text-2xl font-bold mb-4">
        Human Music Platform
      </h1>

      <pre className="bg-gray-100 p-4 rounded mb-4">
        {JSON.stringify(balance, null, 2)}
      </pre>

      <button
        onClick={handleStream}
        disabled={loading}
        className="px-4 py-2 bg-black text-white rounded"
      >
        {loading ? "Processing..." : "Play Song (Stream)"}
      </button>
    </main>
  );
}