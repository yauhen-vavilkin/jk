// Where a saved job dragged over the board would land.
import type { Collision } from "@dnd-kit/core";

export interface InsertPlace {
  flowId: string;
  /** The step number it would take; the number of steps means the end. */
  index: number;
}

/** What a card, the slot standing open, and the add slot say about themselves. */
interface InsertData {
  insertInto: string;
  index: number;
}

/**
 * The slot standing open and the add slot are a place; a card is two, the one
 * before it on its left half and the one after it on its right half.
 */
function placeOf(hit: Collision, pointerX: number | null): InsertPlace | null {
  const container = hit.data?.droppableContainer;
  const data = container?.data?.current as InsertData | undefined;
  if (!data?.insertInto) return null;
  const rect = container?.rect?.current as { left: number; width: number } | null | undefined;
  const card = !/^(slot|add):/.test(String(hit.id));
  const after = card && pointerX !== null && rect && pointerX >= rect.left + rect.width / 2;
  return { flowId: data.insertInto, index: after ? data.index + 1 : data.index };
}

/**
 * The place under the pointer. The slot already standing open keeps it, and so
 * does the gap between two cards. That is what stops the cards from flitting
 * between two places while the pointer stands still. Anywhere else on a flow
 * means the end.
 */
export function insertTarget(
  collisions: Collision[] | null,
  current: InsertPlace | null,
  endOf: (flowId: string) => number | null,
  pointerX: number | null = null,
): InsertPlace | null {
  const hits = collisions ?? [];
  for (const hit of hits) {
    const place = placeOf(hit, pointerX);
    if (place) return same(place, current) ? current : place;
  }
  for (const hit of hits) {
    const id = String(hit.id);
    if (!id.startsWith("flow:")) continue;
    const flowId = id.slice(5);
    if (current?.flowId === flowId) return current;
    const end = endOf(flowId);
    return end === null ? null : { flowId, index: end };
  }
  return null;
}

function same(place: InsertPlace, current: InsertPlace | null): current is InsertPlace {
  return current !== null && current.flowId === place.flowId && current.index === place.index;
}
