import { describe, expect, it } from "vitest";

import type { Flow } from "@/api/types";
import { acceptsAStep, canChangeSteps, hasEnded, isActive } from "./flowState";

const flow = (status: Flow["status"], editing = false) => ({ status, editing }) as Flow;

describe("what a flow is at this moment", () => {
  it("takes a step while it is edited, and while it is going", () => {
    expect(acceptsAStep(flow("draft", true))).toBe(true);
    // Built already: it is closed until the user opens it again.
    expect(acceptsAStep(flow("draft"))).toBe(false);
    expect(acceptsAStep(flow("running"))).toBe(true);
    expect(acceptsAStep(flow("stopped"))).toBe(true);
    expect(acceptsAStep(flow("finished"))).toBe(false);
  });

  it("lets a draft being built and a flow still going change, never a record", () => {
    // Editing was turned off to run it; that must not close a running flow.
    expect(canChangeSteps(flow("running"))).toBe(true);
    expect(canChangeSteps(flow("stopped"))).toBe(true);
    expect(canChangeSteps(flow("draft"))).toBe(false);
    expect(canChangeSteps(flow("draft", true))).toBe(true);
    expect(canChangeSteps(flow("failed"))).toBe(false);
    expect(canChangeSteps(flow("finished"))).toBe(false);
  });

  it("has ended once it is a record of a run", () => {
    expect(hasEnded(flow("finished"))).toBe(true);
    expect(hasEnded(flow("failed"))).toBe(true);
    expect(hasEnded(flow("stopped"))).toBe(false);
    expect(isActive(flow("stopped"))).toBe(true);
    expect(isActive(flow("finished"))).toBe(false);
  });
});
