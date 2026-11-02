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
