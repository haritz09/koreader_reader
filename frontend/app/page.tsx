"use client";

import { useRouter } from "next/navigation";
import { BookGrid } from "@/components/book-grid";

export default function Home() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-[#F5F3EE] px-6 py-8 md:px-12 lg:px-16">
      <div className="mx-auto max-w-7xl">
        <header className="mb-10">
          <h1 className="text-4xl font-bold text-gray-900">Library</h1>
          <p className="mt-2 text-sm text-gray-600">
            Continue a story, or add something new.
          </p>
        </header>

        <BookGrid onSelectBook={(bookId) => router.push(`/books/${bookId}`)} />
      </div>
    </main>
  );
}
