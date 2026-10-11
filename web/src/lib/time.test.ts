import { describe, expect, it } from "vitest";

import { clock, elapsed, estimateFraction, estimateText } from "./time";

describe("elapsed", () => {
  it("counts seconds, then minutes, then hours", () => {
    expect(elapsed(41_000)).toBe("41s");
    expect(elapsed(2_472_000)).toBe("41m 12s");
    expect(elapsed(3_840_000)).toBe("1h 04m");
  });

  it("says nothing when there is nothing to say", () => {
    expect(elapsed(null)).toBe("");
    expect(elapsed(-1)).toBe("");
  });
});

describe("estimateText", () => {
  it("marks the estimate, never the time so far, and is never a percentage", () => {
    expect(estimateText(1_320_000, 2_760_000)).toBe("22m of ~46m");
  });

  it("is empty when Jenkins reported no estimate", () => {
    expect(estimateText(1000, null)).toBe("");
    expect(estimateText(1000, 0)).toBe("");
  });
});

describe("estimateFraction", () => {
  it("never shows more than a full bar", () => {
    expect(estimateFraction(1000, 2000)).toBe(0.5);
    expect(estimateFraction(9000, 2000)).toBe(1);
    expect(estimateFraction(null, 2000)).toBe(0);
  });
});

describe("clock", () => {
  it("is empty for a missing time", () => {
    expect(clock(null)).toBe("");
  });

  it("reads the local hour and minute", () => {
    expect(clock(new Date(2026, 0, 2, 14, 2).toISOString())).toBe("14:02");
  });
});
