import type { Active } from "@dnd-kit/core";
import { describe, expect, it } from "vitest";

import { boardAnnouncements, landed, pickedUp } from "./announcements";

const NAMES: Record<string, string> = { "preset:cypress-4-workers": "EDEV Cypress / 4 workers" };
const active = (id: string) => ({ id }) as Active;

describe("what a screen reader hears during a drag", () => {
  it("names what was picked up", () => {
    expect(pickedUp("EDEV Cypress / 4 workers")).toBe("Picked up EDEV Cypress / 4 workers.");
  });

  it("says where it landed, by names", () => {
    const name = "EDEV Cypress / 4 workers";
    expect(landed(name, { kind: "step", step: 3, flow: "Rebuild from my branch and test" })).toBe(
      "EDEV Cypress / 4 workers added as step 3 of Rebuild from my branch and test.",
    );
    expect(landed("Nightly", { kind: "flow", flow: "Rebuild" })).toBe("Nightly added to Rebuild.");
    expect(landed(name, { kind: "new" })).toBe("EDEV Cypress / 4 workers added as a new flow.");
    expect(landed(name, { kind: "moved", step: 2 })).toBe("EDEV Cypress / 4 workers moved to step 2.");
    expect(landed(name, null)).toBe("EDEV Cypress / 4 workers put back.");
  });

  it("uses the names the board gives, never the ids", () => {
    const said = boardAnnouncements(
      (id) => NAMES[id] ?? id,
      () => "EDEV Cypress / 4 workers added as a new flow.",
    );
    const start = said.onDragStart({ active: active("preset:cypress-4-workers") });
    expect(start).toBe("Picked up EDEV Cypress / 4 workers.");
    expect(said.onDragOver({ active: active("preset:cypress-4-workers"), over: null })).toBeUndefined();
    expect(said.onDragEnd({ active: active("preset:cypress-4-workers"), over: null })).toBe(
      "EDEV Cypress / 4 workers added as a new flow.",
    );
    expect(said.onDragCancel({ active: active("preset:cypress-4-workers"), over: null })).toBe(
      "EDEV Cypress / 4 workers put back.",
    );
  });
});
