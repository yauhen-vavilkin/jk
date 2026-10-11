import { describe, expect, it } from "vitest";

import { nextActive } from "./Search";

describe("nextActive", () => {
  it("walks the results with the arrow keys and wraps round at either end", () => {
    expect(nextActive(0, 3, "ArrowDown")).toBe(1);
    expect(nextActive(2, 3, "ArrowDown")).toBe(0);
    expect(nextActive(0, 3, "ArrowUp")).toBe(2);
    expect(nextActive(2, 3, "ArrowUp")).toBe(1);
  });

  it("starts from the top when nothing is marked yet", () => {
    expect(nextActive(-1, 3, "ArrowDown")).toBe(0);
    expect(nextActive(-1, 3, "ArrowUp")).toBe(2);
  });

  it("marks nothing when there is nothing to mark", () => {
    expect(nextActive(0, 0, "ArrowDown")).toBe(-1);
  });
});
