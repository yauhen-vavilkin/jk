import { describe, expect, it } from "vitest";

import type { Step } from "@/api/types";
import { notStarted, statusOf } from "./cardMetrics";

const step = (patch: Partial<Step>): Step =>
  ({ position: 0, state: "planned", held: false, ...patch }) as Step;

describe("statusOf", () => {
  it("says a step ended without a linked build is not linked", () => {
    expect(statusOf(step({ state: "closed" })).word).toBe("not linked");
  });

  it("says a step a failed or finished flow did not reach is not started", () => {
    for (const flowStatus of ["failed", "finished"] as const) {
      expect(notStarted(step({}), flowStatus)).toBe(true);
      expect(statusOf(step({}), flowStatus)).toMatchObject({ word: "not started", wordClass: "text-dim" });
    }
  });

  it("still says waiting on a flow that may yet reach the step", () => {
    for (const flowStatus of ["running", "stopped", undefined] as const) {
      expect(notStarted(step({}), flowStatus)).toBe(false);
      expect(statusOf(step({}), flowStatus).word).toBe("waiting");
    }
    expect(statusOf(step({ state: "SUCCESS" }), "failed").word).toBe("SUCCESS");
  });
});
