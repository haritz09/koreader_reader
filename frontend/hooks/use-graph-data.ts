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
    setLoading(true);
    fetchGraph();
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    const es = new EventSource(`${apiBase}/ebooks/${bookId}/position-events`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "position") {
        fetchGraph();
      }
    };
    return () => es.close();
  }, [fetchGraph, bookId]);

  return { graph, loading, error, refetch: fetchGraph };
}
