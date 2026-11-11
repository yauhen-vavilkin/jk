import { describe, expect, it } from "vitest";

import type { ParamSetting, Preset } from "@/api/types";
import { launchMark } from "./PresetCard";

const job = (params: Record<string, ParamSetting["mode"]>): Preset =>
  ({
    params: Object.fromEntries(Object.entries(params).map(([name, mode]) => [name, { mode, value: "" }])),
  }) as unknown as Preset;

describe("a saved job's launch mark", () => {
  it("counts the values asked at launch", () => {
    expect(launchMark(job({ BRANCH: "ask" }))).toBe("1 at launch");
    expect(launchMark(job({ BRANCH: "ask", CLUSTER: "ask", NAMESPACE: "ask", TENANT: "fixed" }))).toBe("3 at launch");
  });

  it("is absent when the job asks for nothing", () => {
    expect(launchMark(job({ TENANT: "fixed", LEFT: "default" }))).toBeNull();
  });
});
