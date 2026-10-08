import type { EbookStatusResponse, KoreaderSyncResponse } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export async function uploadEbook(file: File): Promise<{ book_id: string; document_hash: string; processing_status: string }> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/ebooks`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `Upload failed: ${res.status}`);
  }

  return res.json();
}

export async function getEbookStatus(bookId: string): Promise<EbookStatusResponse> {
  const res = await fetch(`${API_BASE}/ebooks/${bookId}`);

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch book: ${res.status}`);
  }

  return res.json();
}

export async function getGraph(bookId: string) {
  const res = await fetch(`${API_BASE}/ebooks/${bookId}/graph`);

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch graph: ${res.status}`);
  }

  return res.json();
}

export async function syncProgress(data: {
  document: string;
  progress: number;
  percentage: number;
  device: string;
}): Promise<KoreaderSyncResponse> {
  const res = await fetch(`${API_BASE}/adapters/koreader/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `Sync failed: ${res.status}`);
  }

  return res.json();
}
