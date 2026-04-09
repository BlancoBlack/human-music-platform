"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export default function Home() {
  const [balance, setBalance] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchBalance = () => {
    fetch("http://127.0.0.1:8000/balance")
      .then((res) => res.json())
      .then((data) => setBalance(data));
  };

  useEffect(() => {
    fetchBalance();
  }, []);

  const handleStream = async () => {
    setLoading(true);

    await fetch("http://127.0.0.1:8000/stream", {
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