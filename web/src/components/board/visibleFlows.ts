import type { Flow } from "@/api/types";

/**
 * The flows not cleared off the board (the server decides when, so the board and
 * the names it holds are one list), in the board's own order: pinned first, then
 * the flow made first. The server lists newest first and the cache appends a new
 * flow last, so their order would flip on a reload. A flow run again keeps the
 * time it was made, so it keeps its place.
 */
export function visibleFlows(flows: Flow[]): Flow[] {
  return [...flows.filter((flow) => !flow.cleared)].sort(
    (left, right) =>
      Number(right.pinned) - Number(left.pinned) ||
      made(left) - made(right) ||
      left.id.localeCompare(right.id),
  );
}

/** Two flows made in the same second go by id, so the board never wavers. */
function made(flow: Flow): number {
  const at = new Date(flow.created_at).getTime();
  return Number.isNaN(at) ? 0 : at;
}
