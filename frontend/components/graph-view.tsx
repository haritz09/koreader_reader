"use client";

import { useState, useEffect, useCallback } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from "reactflow";
import "reactflow/dist/style.css";
import { getGraph } from "@/lib/api";
import type { GraphNodeResponse } from "@/types/api";

interface GraphViewProps {
  bookId: string;
}

const nodeColors: Record<string, string> = {
  character: "#a3e635",
  location: "#60a5fa",
  event: "#f472b6",
  organization: "#fbbf24",
  artifact: "#c084fc",
  concept: "#34d399",
  other: "#9ca3af",
};

export function GraphView({ bookId }: GraphViewProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    try {
      setError(null);
      const data = await getGraph(bookId);

      const flowNodes: Node[] = data.nodes.map((node: GraphNodeResponse) => ({
        id: node.node_id,
        position: { x: Math.random() * 400, y: Math.random() * 400 },
        data: {
          label: node.label,
          nodeType: node.node_type,
          description: node.description,
          importance: node.importance,
        },
        style: {
          background: nodeColors[node.node_type] || nodeColors.other,
          color: "#000",
          border: "none",
          borderRadius: "8px",
          padding: "8px 12px",
          fontSize: "12px",
          fontWeight: 600,
        },
      }));

      const flowEdges: Edge[] = data.edges.map((edge) => ({
        id: edge.edge_id,
        source: edge.source_id,
        target: edge.target_id,
        label: edge.statement,
        animated: true,
        style: { stroke: "#666", strokeWidth: 1.5 },
        labelStyle: { fontSize: 10, fill: "#666" },
        labelBgStyle: { fill: "#fff", fillOpacity: 0.8 },
      }));

      setNodes(flowNodes);
      setEdges(flowEdges);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar grafo");
    } finally {
      setLoading(false);
    }
  }, [bookId]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  if (loading) {
    return (
      <div className="flex h-[600px] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[600px] flex-col items-center justify-center">
        <p className="text-sm text-red-500">{error}</p>
        <button
          onClick={fetchGraph}
          className="mt-4 rounded-md bg-accent px-4 py-2 text-sm text-black hover:bg-accent-hover"
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="h-[600px] w-full rounded-lg border border-gray-200 dark:border-gray-700">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        attributionPosition="bottom-left"
      >
        <Background color="#aaa" gap={16} />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            const type = n.data?.nodeType;
            return nodeColors[type as string] || nodeColors.other;
          }}
        />
      </ReactFlow>
    </div>
  );
}
