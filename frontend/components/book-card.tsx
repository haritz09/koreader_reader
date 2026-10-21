"use client";

import { useState } from "react";
import { deleteEbook, retryEbook } from "@/lib/api";
import type { EbookStatusResponse } from "@/types/api";

interface BookCardProps {
  book: EbookStatusResponse;
  onSelect: (bookId: string) => void;
  onRetry: (bookId: string) => void;
  onDelete: () => void;
  index?: number;
}

export function BookCard({
  book,
  onSelect,
  onRetry,
  onDelete,
  index = 0,
}: BookCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const progressPercent = Math.round(book.progress_position * 100);
  const isProcessing = book.processing_status === "processing";

  const closeMenu = () => {
    setMenuOpen(false);
    setConfirmingDelete(false);
    setDeleteError(null);
  };

  const toggleMenu = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (menuOpen) {
      closeMenu();
      return;
    }
    setMenuOpen(true);
  };

  const statusLabel =
    book.processing_status === "ready"
      ? null
      : book.processing_status === "processing"
        ? "Procesando..."
        : book.processing_status === "failed"
          ? "Error"
          : "Pendiente";

  const handleRetry = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setRetrying(true);
    try {
      await retryEbook(book.book_id);
      onRetry(book.book_id);
    } catch (err) {
      console.error("Retry failed:", err);
    } finally {
      setRetrying(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteEbook(book.book_id);
      closeMenu();
      onDelete();
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : "No se pudo eliminar el libro"
      );
    } finally {
      setDeleting(false);
    }
  };

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
        {book.processing_status === "failed" && (
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="absolute bottom-2 left-2 right-2 rounded-md bg-white/90 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-white disabled:opacity-50 dark:bg-gray-900/90 dark:text-gray-200 dark:hover:bg-gray-900"
          >
            {retrying ? "Reintentando..." : "Reintentar"}
          </button>
        )}
        <button
          className="absolute right-2 top-2 rounded-full bg-white/80 p-1 opacity-0 transition-opacity group-hover:opacity-100 dark:bg-gray-900/80"
          onClick={toggleMenu}
        >
          <svg className="h-4 w-4 text-gray-600 dark:text-gray-300" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
          </svg>
        </button>
        {menuOpen && (
          <div
            className="absolute right-2 top-10 z-10 w-56 rounded-md bg-white py-1 text-left shadow-lg ring-1 ring-black/5 dark:bg-gray-800 dark:ring-white/10"
            onClick={(e) => e.stopPropagation()}
          >
            {confirmingDelete ? (
              <div className="px-4 py-3">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  ¿Eliminar este libro?
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Se quitará de tu biblioteca. Podrás volver a subirlo después.
                </p>
                {deleteError && (
                  <p className="mt-2 text-xs text-red-500">{deleteError}</p>
                )}
                <div className="mt-3 flex justify-end gap-2">
                  <button
                    onClick={() => {
                      setConfirmingDelete(false);
                      setDeleteError(null);
                    }}
                    disabled={deleting}
                    className="rounded-md px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-gray-700"
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {deleting ? "Eliminando..." : "Eliminar"}
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => {
                  setConfirmingDelete(true);
                  setDeleteError(null);
                }}
                disabled={isProcessing}
                title={
                  isProcessing
                    ? "No se puede eliminar mientras se procesa"
                    : undefined
                }
                className="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                Eliminar
              </button>
            )}
          </div>
        )}
      </div>
      <div className="mt-3">
        <div className="flex items-start justify-between">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {book.title ?? "Sin título"}
          </h3>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {book.author ?? "Autor desconocido"}
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
