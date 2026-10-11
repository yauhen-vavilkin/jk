// What the review says: the values still empty, the window's words, other flows
// on the same target, and why there is no review at all.
import { fireEvent, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import type { Flow, Review, SameTarget } from "@/api/types";
import ReviewRun, { CANT_RUN, errorText, missingText, reviewWords, sameTargetLine } from "./ReviewRun";

const review = { ok: true, issues: [], same_target: [], missing_run_values: [], steps: [
  { step_id: "s1", position: 0, sent: [{ name: "NAMESPACE", value: "saved", per_run: true }], defaults: [] },
] } as unknown as Review;
vi.mock("@/api/queries", () => ({ useReview: () => ({ data: review, isPending: false, error: null }) }));

describe("the review's missing values", () => {
  it("names each empty value and the step it belongs to", () => {
    const steps = [
      { step_id: "a", position: 0 },
      { step_id: "b", position: 1 },
    ];
    expect(missingText([{ step_id: "b", names: ["NAMESPACE"] }], steps)).toBe("Fill NAMESPACE in step 2");
    expect(
      missingText(
        [
          { step_id: "a", names: ["CLUSTER", "NAMESPACE"] },
          { step_id: "b", names: ["NAMESPACE"] },
        ],
        steps,
      ),
    ).toBe("Fill CLUSTER, NAMESPACE in step 1; NAMESPACE in step 2");
  });
});

describe("a value typed in the review", () => {
  it("stays when another step of the flow changes", () => {
    const flow = (condition: string) =>
      ({ id: "f", steps: [{ id: "s1", run_values: { NAMESPACE: "saved" } }, { id: "s2", condition }] }) as unknown as Flow;
    const show = (condition: string) =>
      createElement(ReviewRun, { flow: flow(condition), scope: { kind: "start" }, onClose: () => {}, onRun: () => {} });
    const { rerender } = render(show("unless_failure"));
    fireEvent.change(screen.getByLabelText("Value for NAMESPACE"), { target: { value: "typed" } });
    rerender(show("always"));
    expect(screen.getByLabelText("Value for NAMESPACE")).toHaveValue("typed");
  });
});

describe("the review's words", () => {
  it("says what the buttons do for steps added to a started flow", () => {
    expect(reviewWords("held", [5])).toEqual({
      title: "Review added step 6",
      button: "Confirm step 6",
      label: "Review added step 6",
      discard: "Remove step 6",
    });
    expect(reviewWords("held", [4, 5])).toMatchObject({
      title: "Review added steps",
      button: "Confirm steps",
      discard: "Remove steps",
    });
  });

  it("calls a resume review Resume", () => {
    expect(reviewWords("resume", [2])).toMatchObject({ title: "Resume", label: "Resume", button: "Resume flow" });
    expect(reviewWords("start", [0])).toMatchObject({ title: "Run", button: "Run flow" });
  });
});

describe("another flow on the same target", () => {
  const other = (state: SameTarget["state"], build_number: number | null = null): SameTarget => ({
    flow_id: "f",
    flow_name: "Nightly",
    position: 1,
    state,
    cluster: "example-cluster",
    namespace: "example-ns",
    build_number,
  });
  const text = (item: SameTarget) => {
    const line = sameTargetLine(item);
    return `${item.flow_name}${line.before}example-cluster / example-ns${line.after}`;
  };

  it("says which step is running, and its build once it has one", () => {
    expect(text(other("running", 9928))).toBe("Nightly is running on example-cluster / example-ns (step 2, #9928).");
    expect(text(other("queued"))).toBe("Nightly is running on example-cluster / example-ns (step 2).");
    expect(sameTargetLine(other("running", 9928)).colour).toBe("text-info");
  });

  it("says a step that needs attention may be running", () => {
    expect(text(other("needs_attention"))).toBe(
      "Nightly may be running on example-cluster / example-ns (step 2 needs attention).",
    );
    expect(sameTargetLine(other("needs_attention")).icon).toBe("alert");
  });

  it("says when a running flow reaches the target later", () => {
    expect(text(other("planned"))).toBe("Nightly reaches example-cluster / example-ns at step 2.");
    expect(sameTargetLine(other("planned")).colour).toBe("text-dim");
  });
});

describe("a review that could not be made", () => {
  it("names JK when JK could not be reached, and JK's own reason otherwise", () => {
    expect(errorText(new TypeError("Failed to fetch"))).toBe("JK could not be reached. Nothing was sent.");
    expect(errorText(new ApiError(0, "unreachable", "JK could not be reached."))).toBe(
      "JK could not be reached. Nothing was sent.",
    );
    expect(errorText(new ApiError(404, "not_found", "JK has no flow."))).toBe("JK has no flow. Nothing was sent.");
    expect(errorText(new ApiError(409, "x", "Review found problems. Nothing was sent."))).toBe(
      "Review found problems. Nothing was sent.",
    );
  });

  it("does not call a job changed in Jenkins a failure", () => {
    expect(CANT_RUN).toBe("Can't run yet. Nothing was sent.");
  });
});
