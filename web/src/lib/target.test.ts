import { describe, expect, it } from "vitest";

import {
  JENKINS_DEFAULTS,
  NOT_CONFIGURED,
  reviewTargetText,
  stepList,
  targetGroups,
  targetText,
} from "./target";

describe("targetText", () => {
  it("joins the two, or says what is missing", () => {
    expect(targetText("example-cluster", "example-ns")).toBe("example-cluster / example-ns");
    expect(targetText("example-cluster", "")).toBe("example-cluster");
    expect(targetText("", "")).toBe(NOT_CONFIGURED);
  });
});

describe("reviewTargetText", () => {
  it("names what is left to Jenkins", () => {
    expect(reviewTargetText("example-cluster", "example-ns")).toBe("example-cluster / example-ns");
    expect(reviewTargetText("example-cluster", "")).toBe("example-cluster / Jenkins default");
    expect(reviewTargetText("", "")).toBe(JENKINS_DEFAULTS);
  });
});

describe("targetGroups", () => {
  it("gives each target its own line and shares a line for the same target", () => {
    expect(
      targetGroups([
        { position: 0, cluster: "example-cluster", namespace: "example-ns" },
        { position: 1, cluster: "example-cluster", namespace: "sprint" },
        { position: 2, cluster: "example-cluster", namespace: " example-ns " },
        { position: 3, cluster: "", namespace: "" },
      ]),
    ).toEqual([
      { steps: "Steps 1 and 3", target: "example-cluster / example-ns" },
      { steps: "Step 2", target: "example-cluster / sprint" },
      { steps: "Step 4", target: "Jenkins defaults" },
    ]);
  });
});

describe("stepList", () => {
  it("names the steps the way the sentence reads", () => {
    expect(stepList([0])).toBe("Step 1");
    expect(stepList([0, 2])).toBe("Steps 1 and 3");
    expect(stepList([3, 0, 1])).toBe("Steps 1, 2 and 4");
    expect(stepList([])).toBe("");
  });
});
