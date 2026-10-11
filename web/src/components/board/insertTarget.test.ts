import type { Collision } from "@dnd-kit/core";
import { describe, expect, it } from "vitest";

import { insertTarget } from "./insertTarget";

// A card 220px wide, starting 100px in unless told otherwise.
const card = (id: string, insertInto: string, index: number, left = 100) =>
  ({
    id,
    data: {
      droppableContainer: {
        data: { current: { insertInto, index } },
        rect: { current: { left, width: 220 } },
      },
    },
  }) as unknown as Collision;
const plain = (id: string) => ({ id }) as Collision;
const endOf = (flowId: string) => (flowId === "f" ? 3 : null);

describe("insertTarget", () => {
  it("gives the place of the card under the pointer, wherever it sits among the hits", () => {
    expect(insertTarget([card("f:1", "f", 1), plain("flow:f")], null, endOf)).toEqual({
      flowId: "f",
      index: 1,
    });
    expect(insertTarget([plain("flow:f"), card("f:2", "f", 2)], null, endOf)).toEqual({
      flowId: "f",
      index: 2,
    });
  });

  it("is the card's own place on its left half and the next one on its right half", () => {
    expect(insertTarget([card("f:1", "f", 1)], null, endOf, 150)).toEqual({ flowId: "f", index: 1 });
    expect(insertTarget([card("f:1", "f", 1)], null, endOf, 250)).toEqual({ flowId: "f", index: 2 });
    // The last card's right half is the end.
    expect(insertTarget([card("f:2", "f", 2)], null, endOf, 300)).toEqual({ flowId: "f", index: 3 });
  });

  it("takes the slot and the add slot as one place, wherever the pointer is on them", () => {
    expect(insertTarget([card("slot:f", "f", 1)], null, endOf, 300)).toEqual({ flowId: "f", index: 1 });
    expect(insertTarget([card("add:f", "f", 3)], null, endOf, 300)).toEqual({ flowId: "f", index: 3 });
  });

  it("keeps the place it already has, so the cards stand still", () => {
    const open = { flowId: "f", index: 1 };

    // The slot standing open, and the gap beside it.
    expect(insertTarget([card("slot:f", "f", 1), plain("flow:f")], open, endOf)).toBe(open);
    expect(insertTarget([plain("flow:f")], open, endOf)).toBe(open);
  });

  it("is the end of a flow the pointer has just come to", () => {
    expect(insertTarget([plain("flow:f")], { flowId: "other", index: 0 }, endOf)).toEqual({
      flowId: "f",
      index: 3,
    });
  });

  it("is nowhere off the flows", () => {
    expect(insertTarget([plain("new-flow")], null, endOf)).toBeNull();
    expect(insertTarget(null, { flowId: "f", index: 1 }, endOf)).toBeNull();
  });
});
