// What a screen reader hears while something is dragged on the board: the names
// the user sees, never the ids dnd-kit knows them by.
import type { Announcements } from "@dnd-kit/core";

/** Where a drag ended: a place in a flow, a new flow, or back where it was (null). */
export type Landing =
  | { kind: "step"; step: number; flow: string }
  | { kind: "flow"; flow: string }
  | { kind: "new" }
  | { kind: "moved"; step: number };

export const pickedUp = (name: string) => `Picked up ${name}.`;

export function landed(name: string, landing: Landing | null): string {
  if (!landing) return `${name} put back.`;
  if (landing.kind === "step") return `${name} added as step ${landing.step} of ${landing.flow}.`;
  if (landing.kind === "flow") return `${name} added to ${landing.flow}.`;
  if (landing.kind === "new") return `${name} added as a new flow.`;
  return `${name} moved to step ${landing.step}.`;
}

/**
 * The board's announcements. `nameOf` names what an id stands for; `ended` is
 * what the drop that just happened did, worked out by the board as it let go.
 */
export function boardAnnouncements(
  nameOf: (id: string) => string,
  ended: () => string | undefined,
): Announcements {
  return {
    onDragStart: ({ active }) => pickedUp(nameOf(String(active.id))),
    // Silent on the way: the drop says where it went.
    onDragOver: () => undefined,
    onDragEnd: () => ended(),
    onDragCancel: ({ active }) => landed(nameOf(String(active.id)), null),
  };
}
