export const PENDING = "pending";
export const PROCESSING = "processing";
export const READY = "ready";
export const PARTIAL = "partial";
export const FAILED = "failed";

export type ProcessingStatus =
  | typeof PENDING
  | typeof PROCESSING
  | typeof READY
  | typeof PARTIAL
  | typeof FAILED;

export const ACTIVE_STATUSES: ReadonlySet<string> = new Set([
  PENDING,
  PROCESSING,
]);

export const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  READY,
  PARTIAL,
  FAILED,
]);

export const GRAPH_STATUSES: ReadonlySet<string> = new Set([READY, PARTIAL]);

export const RETRYABLE_STATUSES: ReadonlySet<string> = new Set([
  FAILED,
  PARTIAL,
]);

export interface ProcessingProgress {
  total: number;
  extracted: number;
}

interface ProgressCounts {
  chunks_total?: number | null;
  chunks_extracted?: number | null;
}

export function extractionPercent(book: ProgressCounts): number | null {
  const total = book.chunks_total ?? 0;
  if (total <= 0) return null;
  const extracted = Math.min(book.chunks_extracted ?? 0, total);
  return Math.round((extracted / total) * 100);
}
