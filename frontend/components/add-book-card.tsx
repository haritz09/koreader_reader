"use client";

import { useState } from "react";
import { uploadEbook } from "@/lib/api";

interface AddBookCardProps {
  onUploaded: () => void;
}

export function AddBookCard({ onUploaded }: AddBookCardProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    if (!file.name.endsWith(".epub")) {
      setError("Solo archivos EPUB");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError("Archivo demasiado grande (máx 50 MB)");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      await uploadEbook(file);
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al subir");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div
      className={`flex aspect-[2/3] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed transition-colors ${
        isDragging
          ? "border-[#5C6B4F] bg-[#5C6B4F]/5"
          : "border-gray-300 bg-gray-50 hover:border-gray-400"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => document.getElementById("file-input")?.click()}
    >
      <input
        id="file-input"
        type="file"
        accept=".epub"
        className="hidden"
        onChange={handleChange}
      />
      {isUploading ? (
        <div className="flex flex-col items-center gap-2">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#5C6B4F] border-t-transparent" />
          <span className="text-xs text-gray-500">Subiendo...</span>
        </div>
      ) : (
        <>
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#5C6B4F]/10">
            <svg className="h-6 w-6 text-[#5C6B4F]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <p className="mt-3 text-sm font-medium text-gray-900">Añadir libro</p>
          <p className="mt-1 text-xs text-gray-500">EPUB hasta 50 MB</p>
        </>
      )}
      {error && (
        <p className="mt-2 text-xs text-red-500">{error}</p>
      )}
    </div>
  );
}
