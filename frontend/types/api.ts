export interface GraphNodeResponse {
  node_id: string;
  label: string;
  node_type: string;
  first_seen_position: number;
  mention_count: number;
  description: string;
  sub_type: string | null;
  aliases: string[];
  importance: number | null;
}

export interface GraphEdgeResponse {
  edge_id: string;
  source_id: string;
  target_id: string;
  statement: string;
  position: number;
  chunk_id: string;
}

export interface GraphResponse {
  book_id: string;
  position: number;
  revision: number;
  nodes: GraphNodeResponse[];
  edges: GraphEdgeResponse[];
}

export interface EbookUploadResponse {
  book_id: string;
  document_hash: string;
  processing_status: string;
}

export interface EbookStatusResponse extends EbookUploadResponse {
  progress_position: number;
  processing_error: string | null;
}

export interface KoreaderSyncRequest {
  document: string;
  progress: number;
  percentage: number;
  device: string;
}

export interface KoreaderSyncResponse {
  book_id: string;
  position: number;
  device: string;
  accepted: boolean;
  graph_revision: number;
  graph_generation_queued: boolean;
}
