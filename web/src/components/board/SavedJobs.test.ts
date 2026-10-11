import { describe, expect, it } from "vitest";

import type { Preset, SavedFlow, SavedFlowStep } from "@/api/types";
import { groupByOperation, savedFlowMeta } from "./SavedJobs";

const saved = (steps: number, estimate_ms: number | null): SavedFlow =>
  ({ steps: Array.from({ length: steps }, () => ({}) as SavedFlowStep), estimate_ms }) as SavedFlow;

const preset = (name: string, operation: string): Preset => ({ id: name, name, operation }) as Preset;

describe("a saved flow's row", () => {
  it("says how many steps it has and how long Jenkins expects them to take", () => {
    expect(savedFlowMeta(saved(2, 5 * 60_000))).toBe("2 steps · ~5m");
  });

  it("says only the steps while Jenkins has no guess for one of them", () => {
    expect(savedFlowMeta(saved(1, null))).toBe("1 step");
  });
});

describe("the saved jobs column", () => {
  it("groups by operation and sorts each group by name, never by the last run", () => {
    const groups = groupByOperation([
      preset("edev-snapshot Cypress / 2 worker", "EDEV"),
      preset("delete name space", "namespace"),
      preset("EDEV Cypress / 4 workers", "edev"),
    ]);
    expect(groups.map(([operation, list]) => [operation, list.map((item) => item.name)])).toEqual([
      ["edev", ["EDEV Cypress / 4 workers", "edev-snapshot Cypress / 2 worker"]],
      ["namespace", ["delete name space"]],
    ]);
  });
});
