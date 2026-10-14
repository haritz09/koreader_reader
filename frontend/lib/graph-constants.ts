export const nodeColors: Record<string, string> = {
  character: "#6b21a8",
  location: "#facc15",
  event: "#f472b6",
  organization: "#fbbf24",
  artifact: "#c084fc",
  concept: "#34d399",
  other: "#9ca3af",
};

export const importanceSizes: Record<number, { width: number; height: number }> = {
  1: { width: 180, height: 80 },
  2: { width: 140, height: 60 },
  3: { width: 100, height: 44 },
};

export const defaultSize = { width: 120, height: 52 };
