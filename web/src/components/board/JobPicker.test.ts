import { describe, expect, it } from "vitest";

import type { Drift, Preset, SavedFlow } from "@/api/types";
import { pickerOptions } from "./JobPicker";

const preset = (name: string, operation: string, drift: Drift | null = null): Preset =>
  ({ id: name, name, operation, drift }) as Preset;
const savedFlow = (name: string): SavedFlow =>
  ({ id: name, name, steps: [{}, {}], estimate_ms: null }) as unknown as SavedFlow;

const PRESETS = [
  preset("delete name space", "namespace"),
  preset("EDEV Cypress / 4 workers", "EDEV"),
  preset("create edev branch", "edev", {} as Drift),
];
const FLOWS = [savedFlow("Rebuild from my branch and test")];

describe("the saved-job picker", () => {
  it("lists saved jobs in the column's order, then saved flows", () => {
    expect(pickerOptions(PRESETS, FLOWS, "").map((option) => [option.label, option.note])).toEqual([
      ["create edev branch", "Jenkins changed it"],
      ["EDEV Cypress / 4 workers", "edev"],
      ["delete name space", "namespace"],
      ["Rebuild from my branch and test", "2 steps"],
    ]);
  });

  it("keeps a saved job Jenkins changed, but it cannot be picked", () => {
    const [changed] = pickerOptions(PRESETS, FLOWS, "branch");
    expect(changed).toMatchObject({ label: "create edev branch", disabled: true });
  });

  it("matches a name or an operation, whatever the case", () => {
    expect(pickerOptions(PRESETS, FLOWS, "  NAMESPACE ").map((option) => option.label)).toEqual([
      "delete name space",
    ]);
    expect(pickerOptions(PRESETS, FLOWS, "rebuild").map((option) => option.picked.kind)).toEqual([
      "saved-flow",
    ]);
    expect(pickerOptions(PRESETS, FLOWS, "nothing like it")).toEqual([]);
  });
});
