import { describe, expect, it } from "vitest";

import type { Flow } from "@/api/types";
import { acceptsAStep, canChangeSteps, hasEnded, isActive } from "./flowState";

const flow = (status: Flow["status"]) => ({ status }) as Flow;

describe("what a flow is at this moment", () => {
  it("takes a step while it is a draft, and while it is going", () => {
    expect(acceptsAStep(flow("draft"))).toBe(true);
    expect(acceptsAStep(flow("running"))).toBe(true);
    expect(acceptsAStep(flow("stopped"))).toBe(true);
    expect(acceptsAStep(flow("finished"))).toBe(false);
  });

  it("lets a draft and a flow still going change, never a record", () => {
    expect(canChangeSteps(flow("running"))).toBe(true);
    expect(canChangeSteps(flow("stopped"))).toBe(true);
    expect(canChangeSteps(flow("draft"))).toBe(true);
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
