import { describe, expect, it } from "vitest";

import { pageOf } from "./TopBar";

describe("pageOf", () => {
  it("names the page a path shows, for the nav and the browser tab", () => {
    expect(pageOf("/")).toBe("Board");
    expect(pageOf("/library")).toBe("Library");
    expect(pageOf("/library/p-1")).toBe("Library");
    expect(pageOf("/history")).toBe("History");
  });

  it("calls any path it does not know the Board, which is what it shows", () => {
    expect(pageOf("/nowhere")).toBe("Board");
  });
});
