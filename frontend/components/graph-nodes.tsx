import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";
import { nodeColors, importanceSizes, defaultSize } from "@/lib/graph-constants";

export function CharacterNode({ data }: NodeProps) {
  const size = data.importance ? importanceSizes[data.importance] || defaultSize : defaultSize;
  return (
    <div
      style={{
        width: size.width,
        height: size.height,
        background: nodeColors.character,
        clipPath: "polygon(15% 0%, 85% 0%, 100% 50%, 85% 100%, 15% 100%, 0% 50%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "8px 20px",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: "#fff" }} />
      <span style={{ color: "#fff", fontSize: 12, fontWeight: 600, textAlign: "center" }}>
        {data.label}
      </span>
      <Handle type="source" position={Position.Right} style={{ background: "#fff" }} />
    </div>
  );
}

export function EventNode({ data }: NodeProps) {
  return (
    <div
      style={{
        width: 80,
        height: 80,
        background: nodeColors.event,
        borderRadius: "50%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 8,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: "#fff" }} />
      <span style={{ color: "#fff", fontSize: 11, fontWeight: 600, textAlign: "center" }}>
        {data.label}
      </span>
      <Handle type="source" position={Position.Right} style={{ background: "#fff" }} />
    </div>
  );
}

export function LocationNode({ data }: NodeProps) {
  return (
    <div style={{ position: "relative", width: 0, height: 0 }}>
      <Handle type="target" position={Position.Left} style={{ background: "#fff" }} />
      <div
        style={{
          width: 0,
          height: 0,
          borderLeft: "40px solid transparent",
          borderRight: "40px solid transparent",
          borderBottom: `70px solid ${nodeColors.location}`,
          position: "relative",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 30,
            left: -20,
            color: "#000",
            fontSize: 10,
            fontWeight: 600,
            width: 40,
            textAlign: "center",
          }}
        >
          {data.label}
        </span>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "#fff", left: 80 }} />
    </div>
  );
}

export function GenericNode({ data }: NodeProps) {
  return (
    <div
      style={{
        background: nodeColors[data.nodeType as string] || nodeColors.other,
        color: "#000",
        border: "none",
        borderRadius: "8px",
        padding: "8px 12px",
        fontSize: "12px",
        fontWeight: 600,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: "#fff" }} />
      {data.label}
      <Handle type="source" position={Position.Right} style={{ background: "#fff" }} />
    </div>
  );
}

export const nodeTypes = {
  character: CharacterNode,
  event: EventNode,
  location: LocationNode,
  organization: GenericNode,
  artifact: GenericNode,
  concept: GenericNode,
  other: GenericNode,
};
