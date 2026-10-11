import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, UNREACHABLE } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("blames JK, not Jenkins, when the request never reached JK", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.get("/flows").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: "unreachable", message: UNREACHABLE });
  });

  it("carries JK's own sentence when JK answered with an error", async () => {
    const body = { error: { code: "flow_editing", message: "Press Done before running this flow." } };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 409 })),
    );
    await expect(api.post("/flows/f-1/start")).rejects.toMatchObject({
      status: 409,
      code: "flow_editing",
      message: "Press Done before running this flow.",
    });
  });
});
