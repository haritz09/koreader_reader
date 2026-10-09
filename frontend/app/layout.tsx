"use client";

import { useState, useEffect } from "react";
import type { Metadata } from "next";
import "./globals.css";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored) {
      setDark(stored === "dark");
    }
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <html lang="es" suppressHydrationWarning>
      <body className="antialiased">
        <button
          onClick={() => setDark(!dark)}
          className="fixed right-4 top-4 z-50 rounded-full p-2 text-sm opacity-50 transition-opacity hover:opacity-100"
          aria-label="Toggle theme"
        >
          {dark ? "☀️" : "🌙"}
        </button>
        {children}
      </body>
    </html>
  );
}
