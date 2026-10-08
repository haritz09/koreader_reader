"use client";

import { useState, useEffect, useCallback } from "react";
import type { EbookListResponse } from "@/types/api";
import { getEbookStatus } from "@/lib/api";
import { BookCard } from "./book-card";
import { AddBookCard } from "./add-book-card";

interface BookGridProps {
  onSelectBook: (bookId: string) => void;
}

export function BookGrid({ onSelectBook }: BookGridProps) {
  const [books, setBooks] = useState<EbookListResponse["books"]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"recent" | "title">("recent");

  const fetchBooks = useCallback(async () => {
    try {
      setError(null);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/ebooks`);
      if (!res.ok) throw new Error(`Error: ${res.status}`);
      const data: EbookListResponse = await res.json();
      setBooks(data.books);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar libros");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBooks();
  }, [fetchBooks]);

  const sortedBooks = [...books].sort((a, b) => {
    if (sortBy === "title") return a.book_id.localeCompare(b.book_id);
    return b.progress_position - a.progress_position;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#5C6B4F] border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-sm text-red-500">{error}</p>
        <button
          onClick={fetchBooks}
          className="mt-4 rounded-md bg-[#5C6B4F] px-4 py-2 text-sm text-white hover:bg-[#4a5740]"
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-gray-900">Todos los libros</h2>
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
            {books.length}
          </span>
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "recent" | "title")}
          className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700"
        >
          <option value="recent">Recientes</option>
          <option value="title">Título</option>
        </select>
      </div>

      <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        <AddBookCard onUploaded={fetchBooks} />
        {sortedBooks.map((book) => (
          <BookCard key={book.book_id} book={book} onSelect={onSelectBook} />
        ))}
      </div>
    </div>
  );
}
