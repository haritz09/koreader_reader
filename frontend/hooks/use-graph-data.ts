"use client";

import { useCallback, useEffect, useState } from "react";
import { getGraph } from "@/lib/api";
import type { GraphResponse } from "@/types/api";

export function useGraphData(bookId: string) {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    try {
      setError(null);
      const data = await getGraph(bookId);
      setGraph(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar grafo");
    } finally {
      setLoading(false);
    }
  }, [bookId]);

  useEffect(() => {
    let cancelled = false;
    let stream: EventSource | null = null;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

    // The first fetch establishes the session cookie, so the stream opens after.
    const start = async () => {
      setLoading(true);
      await fetchGraph();
      if (cancelled) return;
      stream = new EventSource(`${apiBase}/ebooks/${bookId}/position-events`, {
        withCredentials: true,
      });
      stream.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === "position") {
          fetchGraph();
        }
      };
    };

    start();
    return () => {
      cancelled = true;
      stream?.close();
    };
  }, [fetchGraph, bookId]);

  return { graph, loading, error, refetch: fetchGraph };
}
