"use client";

import { useState } from "react";
import type { EbookStatusResponse } from "@/types/api";

interface BookCardProps {
  book: EbookStatusResponse;
  onSelect: (bookId: string) => void;
}

export function BookCard({ book, onSelect }: BookCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const progressPercent = Math.round(book.progress_position * 100);

  return (
    <div
      className="group cursor-pointer"
      onClick={() => onSelect(book.book_id)}
    >
      <div className="relative aspect-[2/3] overflow-hidden rounded-lg bg-gray-200 shadow-sm transition-shadow group-hover:shadow-md">
        <div className="flex h-full items-center justify-center bg-gradient-to-br from-gray-100 to-gray-200">
          <span className="text-xs text-gray-400">Sin portada</span>
        </div>
        <button
          className="absolute right-2 top-2 rounded-full bg-white/80 p-1 opacity-0 transition-opacity group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen(!menuOpen);
          }}
        >
          <svg className="h-4 w-4 text-gray-600" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
          </svg>
        </button>
        {menuOpen && (
          <div className="absolute right-2 top-10 z-10 rounded-md bg-white py-1 shadow-lg ring-1 ring-black/5">
            <button className="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100">
              Eliminar
            </button>
          </div>
        )}
      </div>
      <div className="mt-3">
        <div className="flex items-start justify-between">
          <h3 className="text-sm font-medium text-gray-900">Libro</h3>
        </div>
        <p className="text-xs text-gray-500">Autor desconocido</p>
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1 flex-1 rounded-full bg-gray-200">
            <div
              className="h-1 rounded-full bg-[#5C6B4F]"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs text-gray-500">{progressPercent}%</span>
        </div>
      </div>
    </div>
  );
}
