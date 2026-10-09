"use client";

import { useState, useEffect, useCallback } from "react";
import { getBooks, streamBookEvents } from "@/lib/api";
import type { EbookStatusResponse } from "@/types/api";
import { BookCard } from "./book-card";
import { AddBookCard } from "./add-book-card";

interface BookGridProps {
  onSelectBook: (bookId: string) => void;
}

export function BookGrid({ onSelectBook }: BookGridProps) {
  const [books, setBooks] = useState<EbookStatusResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"recent" | "title">("recent");

  const fetchBooks = useCallback(async () => {
    try {
      setError(null);
      const data = await getBooks();
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

  useEffect(() => {
    const processingBooks = books.filter(
      (b) => b.processing_status === "processing" || b.processing_status === "pending"
    );
    if (processingBooks.length === 0) return;

    const cleanups = processingBooks.map((book) =>
      streamBookEvents(
        book.book_id,
        (status, error) => {
          setBooks((prev) =>
            prev.map((b) =>
              b.book_id === book.book_id
                ? { ...b, processing_status: status, processing_error: error }
                : b
            )
          );
        },
        fetchBooks
      )
    );

    return () => cleanups.forEach((fn) => fn());
  }, [books, fetchBooks]);

  const sortedBooks = [...books].sort((a, b) => {
    if (sortBy === "title") return a.book_id.localeCompare(b.book_id);
    return b.progress_position - a.progress_position;
  });

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="skeleton-shimmer aspect-[2/3] rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-sm text-red-500">{error}</p>
        <button
          onClick={fetchBooks}
          className="mt-4 rounded-md bg-accent px-4 py-2 text-sm text-black hover:bg-accent-hover"
        >
          Reintentar
        </button>
      </div>
    );
  }

  if (books.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/10">
          <svg className="h-8 w-8 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        </div>
        <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-gray-100">
          Tu biblioteca está vacía
        </h3>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          Sube tu primer EPUB para empezar
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Todos los libros
          </h2>
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
            {books.length}
          </span>
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "recent" | "title")}
          className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
        >
          <option value="recent">Recientes</option>
          <option value="title">Título</option>
        </select>
      </div>

      <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        <AddBookCard onUploaded={fetchBooks} />
        {sortedBooks.map((book, i) => (
          <BookCard key={book.book_id} book={book} onSelect={onSelectBook} index={i} />
        ))}
      </div>
    </div>
  );
}
