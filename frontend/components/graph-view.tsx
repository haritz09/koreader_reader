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
import { useGraphData } from "@/hooks/use-graph-data";
import { nodeColors } from "@/lib/graph-constants";
import { nodeTypes } from "@/components/graph-nodes";
import type { GraphNodeResponse } from "@/types/api";

interface GraphViewProps {
  bookId: string;
}

interface PopupData {
  label: string;
  nodeType: string;
  subType: string | null;
  aliases: string[];
  description: string;
}

export function GraphView({ bookId }: GraphViewProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [popup, setPopup] = useState<PopupData | null>(null);
  const { graph, loading, error, refetch } = useGraphData(bookId);

  useEffect(() => {
    if (!graph) return;

    const flowNodes: Node[] = graph.nodes.map((node: GraphNodeResponse) => ({
      id: node.node_id,
      type: node.node_type in nodeTypes ? node.node_type : "other",
      position: { x: Math.random() * 400, y: Math.random() * 400 },
      data: {
        label: node.label,
        nodeType: node.node_type,
        description: node.description,
        sub_type: node.sub_type,
        aliases: node.aliases,
        importance: node.importance,
      },
    }));

    const flowEdges: Edge[] = graph.edges.map((edge) => ({
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
  }, [graph]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setPopup({
      label: node.data.label,
      nodeType: node.data.nodeType,
      subType: node.data.sub_type,
      aliases: node.data.aliases || [],
      description: node.data.description,
    });
  }, []);

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
          onClick={refetch}
          className="mt-4 rounded-md bg-accent px-4 py-2 text-sm text-black hover:bg-accent-hover"
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="relative h-[600px] w-full rounded-lg border border-gray-200 dark:border-gray-700">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
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
      {popup && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40">
          <div className="mx-4 w-full max-w-md rounded-xl bg-white p-6 shadow-2xl dark:bg-gray-800">
            <div className="flex items-start justify-between">
              <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
                {popup.label}
              </h3>
              <button
                onClick={() => setPopup(null)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
              >
                ✕
              </button>
            </div>
            <dl className="mt-4 space-y-3">
              <div>
                <dt className="text-xs font-medium uppercase text-gray-500">Type</dt>
                <dd className="text-sm capitalize text-gray-900 dark:text-gray-100">{popup.nodeType}</dd>
              </div>
              {popup.subType && (
                <div>
                  <dt className="text-xs font-medium uppercase text-gray-500">Subtype</dt>
                  <dd className="text-sm text-gray-900 dark:text-gray-100">{popup.subType}</dd>
                </div>
              )}
              {popup.aliases.length > 0 && (
                <div>
                  <dt className="text-xs font-medium uppercase text-gray-500">Aliases</dt>
                  <dd className="text-sm text-gray-900 dark:text-gray-100">
                    {popup.aliases.join(", ")}
                  </dd>
                </div>
              )}
              {popup.description && (
                <div>
                  <dt className="text-xs font-medium uppercase text-gray-500">Description</dt>
                  <dd className="text-sm text-gray-900 dark:text-gray-100">{popup.description}</dd>
                </div>
              )}
            </dl>
            <button
              onClick={() => setPopup(null)}
              className="mt-6 w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-black hover:bg-accent-hover"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
