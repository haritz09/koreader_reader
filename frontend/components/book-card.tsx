"use client";

import { useState } from "react";
import type { EbookStatusResponse } from "@/types/api";

interface BookCardProps {
  book: EbookStatusResponse;
  onSelect: (bookId: string) => void;
  index?: number;
}

export function BookCard({ book, onSelect, index = 0 }: BookCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const progressPercent = Math.round(book.progress_position * 100);

  const statusLabel =
    book.processing_status === "ready"
      ? null
      : book.processing_status === "processing"
        ? "Procesando..."
        : book.processing_status === "failed"
          ? "Error"
          : "Pendiente";

  return (
    <div
      className="group cursor-pointer animate-fade-in-up"
      style={{ animationDelay: `${index * 50}ms` }}
      onClick={() => book.processing_status === "ready" && onSelect(book.book_id)}
    >
      <div className="relative aspect-[2/3] overflow-hidden rounded-lg bg-gray-200 shadow-sm transition-all duration-200 group-hover:-translate-y-1 group-hover:shadow-md dark:bg-gray-800">
        {book.cover_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={book.cover_url}
            alt="Portada"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-700">
            <span className="text-xs text-gray-400">Sin portada</span>
          </div>
        )}
        {statusLabel && (
          <div className="absolute left-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-xs text-white">
            {statusLabel}
          </div>
        )}
        <button
          className="absolute right-2 top-2 rounded-full bg-white/80 p-1 opacity-0 transition-opacity group-hover:opacity-100 dark:bg-gray-900/80"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen(!menuOpen);
          }}
        >
          <svg className="h-4 w-4 text-gray-600 dark:text-gray-300" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
          </svg>
        </button>
        {menuOpen && (
          <div className="absolute right-2 top-10 z-10 rounded-md bg-white py-1 shadow-lg ring-1 ring-black/5 dark:bg-gray-800 dark:ring-white/10">
            <button className="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-700">
              Eliminar
            </button>
          </div>
        )}
      </div>
      <div className="mt-3">
        <div className="flex items-start justify-between">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Libro
          </h3>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Autor desconocido
        </p>
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1 flex-1 rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className="h-1 rounded-full bg-accent"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {progressPercent}%
          </span>
        </div>
      </div>
    </div>
  );
}
