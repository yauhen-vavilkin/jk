// Ending a flow that needs attention names a matching build that still runs, and
// linking a build resumes only a flow that is not stopped.
import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

import type { AttentionCandidate, Flow, Step } from "@/api/types";
import NeedsAttention, { endQuestion } from "./NeedsAttention";

const build = (number: number, state: string) =>
  ({ number, state, time: "", detail: "", url: "" }) as AttentionCandidate;

vi.mock("@/api/queries", () => ({
  useAttention: () => ({ data: { candidates: [build(9928, "RUNNING")] }, isPending: false }),
}));

describe("the End flow question", () => {
  it("names the first matching build still running", () => {
    expect(endQuestion([build(9927, "FAILURE"), build(9928, "RUNNING"), build(9929, "RUNNING")])).toBe(
      "End flow? #9928 may still be running.",
    );
  });

  it("says nothing is sent when no matching build runs", () => {
    expect(endQuestion([build(9927, "SUCCESS")])).toBe("End flow? Nothing is sent.");
    expect(endQuestion([])).toBe("End flow? Nothing is sent.");
  });
});

describe("the link button", () => {
  it("does not promise to resume a stopped flow", () => {
    const flow = { id: "f", name: "Nightly", status: "stopped", steps: [] } as unknown as Flow;
    const step = { id: "s1", position: 0, preset_name: "Create" } as unknown as Step;
    const noop = () => {};
    render(createElement(NeedsAttention, { flow, step, onClose: noop, onLink: noop, onCloseRun: noop }));
    expect(screen.getByRole("button", { name: "Link #9928" })).toBeInTheDocument();
  });
});
