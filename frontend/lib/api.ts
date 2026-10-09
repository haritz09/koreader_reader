import type {
  EbookListResponse,
  EbookStatusResponse,
  GraphResponse,
  KoreaderSyncResponse,
} from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function parseError(res: Response): Promise<string> {
  const error = await res.json().catch(() => ({}));
  return error.detail || `Request failed: ${res.status}`;
}

export async function uploadEbook(
  file: File,
  onProgress?: (percent: number) => void
): Promise<{ book_id: string; document_hash: string; processing_status: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload failed: ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network error")));
    xhr.open("POST", `${API_BASE}/ebooks`);
    xhr.send(formData);
  });
}

export async function getBooks(): Promise<EbookListResponse> {
  const res = await fetch(`${API_BASE}/ebooks`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getEbookStatus(bookId: string): Promise<EbookStatusResponse> {
  const res = await fetch(`${API_BASE}/ebooks/${bookId}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getGraph(bookId: string): Promise<GraphResponse> {
  const res = await fetch(`${API_BASE}/ebooks/${bookId}/graph`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export function streamBookEvents(
  bookId: string,
  onStatus: (status: string, error: string | null) => void,
  onDone: () => void
): () => void {
  const es = new EventSource(`${API_BASE}/ebooks/${bookId}/events`);

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === "status") {
      onStatus(data.status, data.error);
      if (data.status === "ready" || data.status === "failed") {
        es.close();
        onDone();
      }
    }
  };

  return () => es.close();
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
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function retryEbook(bookId: string): Promise<{ book_id: string; processing_status: string }> {
  const res = await fetch(`${API_BASE}/ebooks/${bookId}/retry`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
