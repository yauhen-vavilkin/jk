import { describe, expect, it } from "vitest";

import type { Flow, Step } from "@/api/types";
import { acceptsAStep, canChangeSteps, hasEnded, isActive, stepIdentity } from "./flowState";

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

describe("stepIdentity", () => {
  const step = (patch: Partial<Step>) =>
    ({ id: "f:1", position: 1, preset_id: "p", added_at: "2026-11-10T10:00:00", run_values: {}, ...patch }) as Step;

  it("tells apart two steps of one saved job added at once by their values, whatever their place", () => {
    const one = step({ run_values: { BRANCH: "a", TENANT: "x" } });
    expect(stepIdentity(one)).toBe(stepIdentity(step({ id: "f:3", position: 3, run_values: { TENANT: "x", BRANCH: "a" } })));
    expect(stepIdentity(one)).not.toBe(stepIdentity(step({ run_values: { BRANCH: "b", TENANT: "x" } })));
    expect(stepIdentity(one)).not.toBe(stepIdentity(step({ preset_id: "q", run_values: one.run_values })));
  });
});
