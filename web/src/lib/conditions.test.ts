import { ArrowRight, Check, ChevronsRight, X } from "lucide-react";
import { describe, expect, it } from "vitest";

import {
  CONDITION_COLOUR,
  CONDITION_ICON,
  CONDITION_LABELS,
  conditionLine,
} from "./conditions";

describe("conditionLine", () => {
  it("says what the default does, except on the first step", () => {
    expect(conditionLine("unless_failure", 1)).toBe("ends the flow if step 2 failed");
    expect(conditionLine("unless_failure", -1)).toBeNull();
  });

  it("names the step it depends on, 1-based", () => {
    expect(conditionLine("after_success", 0)).toBe("skipped unless step 1 succeeded");
    expect(conditionLine("always", 2)).toBe("even if step 3 failed");
    expect(conditionLine("after_failure", 1)).toBe("skipped unless step 2 failed");
  });

  it("names no step 0 on the first step of a flow", () => {
    expect(conditionLine("always", -1)).toBe("even if the step before failed");
  });
});

describe("what a condition looks like", () => {
  it("names what happens when the step before did not succeed", () => {
    expect(CONDITION_LABELS.unless_failure).toBe("End the flow if the step before failed");
    expect(CONDITION_LABELS.after_success).toBe("Skip unless the step before succeeded");
    expect(CONDITION_LABELS.always).toBe("Start even if the step before failed");
    expect(CONDITION_LABELS.after_failure).toBe("Skip unless the step before failed");
  });

  it("pairs each condition with the icon and colour of its meaning", () => {
    expect(CONDITION_ICON.unless_failure).toBe(ArrowRight);
    expect(CONDITION_ICON.after_success).toBe(Check);
    expect(CONDITION_ICON.always).toBe(ChevronsRight);
    expect(CONDITION_ICON.after_failure).toBe(X);
    expect(CONDITION_COLOUR.unless_failure.text).toBe("text-dim");
    expect(CONDITION_COLOUR.after_success.text).toBe("text-ok");
    expect(CONDITION_COLOUR.always.text).toBe("text-accent");
    expect(CONDITION_COLOUR.after_failure.text).toBe("text-warn");
  });
});
