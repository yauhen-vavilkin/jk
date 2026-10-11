import { describe, expect, it } from "vitest";

import type { Flow } from "@/api/types";
import { dayClock, rowTime, startedLine } from "./when";

// Local times, so the tests hold in any time zone.
const at = (month: number, day: number, hour: number, minute: number, second = 0, year = 2026) =>
  new Date(year, month - 1, day, hour, minute, second).toISOString();
const NOW = new Date(2026, 8, 30, 12, 0);

const flow = (patch: Partial<Flow>): Flow =>
  ({
    started_at: null,
    finished_at: null,
    updated_at: at(9, 30, 11, 0),
    ...patch,
  }) as Flow;

describe("dayClock", () => {
  it("is the clock alone for today", () => {
    expect(dayClock(at(9, 30, 9, 5), NOW)).toBe("09:05");
  });

  it("names the day for an earlier one, and the year for an earlier year", () => {
    expect(dayClock(at(9, 26, 22, 31), NOW)).toBe("26 Sep 22:31");
    expect(dayClock(at(12, 3, 8, 15, 0, 2025), NOW)).toBe("3 Dec 2025 08:15");
  });

  it("is empty for a missing time", () => {
    expect(dayClock(null, NOW)).toBe("");
  });
});

describe("rowTime", () => {
  it("says when a run finished, else when it last changed", () => {
    expect(rowTime(flow({ finished_at: at(9, 26, 22, 31) }), NOW)).toBe("finished 26 Sep 22:31");
    expect(rowTime(flow({ updated_at: at(9, 30, 11, 40) }), NOW)).toBe("updated 11:40");
  });
});

describe("startedLine", () => {
  it("says when the run began and how long it took", () => {
    const run = flow({ started_at: at(9, 26, 22, 5), finished_at: at(9, 26, 22, 31, 12) });
    expect(startedLine(run, NOW)).toBe("started 26 Sep 22:05 · 26m 12s");
  });

  it("counts a run that is still going up to now", () => {
    expect(startedLine(flow({ started_at: at(9, 30, 11, 50) }), NOW)).toBe("started 11:50 · 10m 00s");
  });

  it("is empty for a run that never started", () => {
    expect(startedLine(flow({}), NOW)).toBe("");
  });
});
