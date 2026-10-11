import { describe, expect, it } from "vitest";

import type { Drift, Flow, SavedFlow, Step } from "@/api/types";
import {
  changedJobsOf,
  fillLabel,
  firstUnfilled,
  headerMetaOf,
  headerStateOf,
  removeWaitsFor,
  reviewJobsLabel,
  saveStateOf,
  stopChoices,
  trashAction,
  unfilledOf,
} from "./headerState";

const step = (patch: Partial<Step>): Step =>
  ({
    position: 0,
    state: "planned",
    build_number: null,
    abort_state: null,
    ...patch,
  }) as Step;

const flow = (patch: Partial<Flow>): Flow =>
  ({
    status: "draft",
    steps: [],
    current_position: null,
    started_at: null,
    finished_at: null,
    ...patch,
  }) as Flow;

describe("headerStateOf", () => {
  it("says a draft the user is building is being edited, in the text colour", () => {
    const state = headerStateOf(flow({ status: "draft", editing: true }));
    expect([state.glyph, state.word, state.tone]).toEqual(["editing", "EDITING", "text-text"]);
  });

  it("says a draft nobody is changing is ready to run", () => {
    const state = headerStateOf(flow({ status: "draft", editing: false }));
    expect([state.glyph, state.word]).toEqual(["ready", "READY"]);
  });

  it("says NOT READY while a value is empty or a saved job changed in Jenkins", () => {
    const built = flow({ status: "draft", editing: false });
    const state = headerStateOf(built, 1);
    expect([state.word, state.tone]).toEqual(["NOT READY", "text-dim"]);
    expect(headerStateOf(built, 0, 2).word).toBe("NOT READY");
    expect(headerStateOf(flow({ status: "draft", editing: true }), 3, 1).word).toBe("EDITING");
  });

  it("names the step that failed, with its own word, past the steps skipped after it", () => {
    const steps = [
      step({ state: "FAILURE" }),
      step({ position: 1, state: "skipped" }),
      step({ position: 2, state: "planned" }),
    ];
    const failed = flow({ status: "failed", failed_at_position: 2, result: "FAILURE", steps });
    expect(headerStateOf(failed).word).toBe("FAILURE at step 1");

    const aborted = [step({ state: "ABORTED" }), step({ position: 1 })];
    expect(headerStateOf(flow({ status: "failed", failed_at_position: 1, steps: aborted })).word).toBe(
      "ABORTED at step 1",
    );
  });

  it("says ENDED, not FAILURE, for a flow the user ended from Needs attention", () => {
    const steps = [step({ state: "SUCCESS" }), step({ position: 1, state: "closed" })];
    const state = headerStateOf(flow({ status: "failed", result: "FAILURE", steps }));
    expect([state.glyph, state.word, state.tone]).toEqual(["stopped", "ENDED", "text-dim"]);
  });

  it("names each saved job Jenkins changed once, in step order", () => {
    const drift = {} as Drift;
    const steps = [
      step({ id: "a", preset_id: "fine" }),
      step({ id: "b", position: 1, preset_id: "changed" }),
      step({ id: "c", position: 2, preset_id: "changed" }),
      step({ id: "d", position: 3, preset_id: "also" }),
    ];
    const driftOf = (item: Step) => (item.preset_id === "fine" ? null : drift);
    expect(changedJobsOf(flow({ steps }), driftOf).map((item) => item.id)).toEqual(["b", "d"]);
    expect(reviewJobsLabel(1)).toBe("Review 1 job");
    expect(reviewJobsLabel(2)).toBe("Review 2 jobs");
  });

  it("counts the values asked at launch that are still empty, blank ones included", () => {
    const asked = () => ["CLUSTER", "NAMESPACE"];
    const steps = [
      step({ run_values: { CLUSTER: "example-cluster", NAMESPACE: " " } }),
      step({ position: 1, run_values: {} }),
    ];
    expect(unfilledOf(flow({ steps }), asked)).toBe(3);
  });

  it("leads to the first step, in order, with a value still empty", () => {
    const asked = (item: Step) => (item.position === 1 ? [] : ["NAMESPACE"]);
    const steps = [
      step({ id: "filled", position: 0, run_values: { NAMESPACE: "example-ns" } }),
      step({ id: "asks nothing", position: 1, run_values: {} }),
      step({ id: "blank", position: 2, run_values: { NAMESPACE: " " } }),
      step({ id: "empty", position: 3, run_values: {} }),
    ];
    expect(firstUnfilled(flow({ steps }), asked)?.id).toBe("blank");
    expect(firstUnfilled(flow({ steps: steps.slice(0, 2) }), asked)).toBeUndefined();
  });

  it("names what stands in for Run by how many values are left", () => {
    expect(fillLabel(1)).toBe("Fill 1 value");
    expect(fillLabel(18)).toBe("Fill 18 values");
  });
});

describe("trashAction", () => {
  it("deletes a draft, which never ran", () => {
    expect(trashAction(flow({ status: "draft" }))).toBe("delete");
  });

  it("clears what ran and ended, so History keeps it", () => {
    expect(trashAction(flow({ status: "finished" }))).toBe("clear");
    expect(trashAction(flow({ status: "failed" }))).toBe("clear");
    expect(trashAction(flow({ status: "stopped", steps: [step({ state: "SUCCESS" })] }))).toBe(
      "clear",
    );
  });

  it("is off while a step waits for a decision, even on a stopped flow", () => {
    const undecided = [step({ state: "SUCCESS" }), step({ position: 1, state: "needs_attention" })];
    expect(trashAction(flow({ status: "stopped", steps: undecided }))).toBe("disabled");
    expect(removeWaitsFor(flow({ status: "stopped", steps: undecided }))).toBe(
      "Resolve step 2 first",
    );
    expect(removeWaitsFor(flow({ status: "needs_attention", steps: undecided }))).toBe(
      "Resolve step 2 first",
    );
  });

  it("says which build a stopped flow's Remove waits for", () => {
    const waits = (going: Partial<Step>) =>
      removeWaitsFor(flow({ status: "stopped", steps: [step({ state: "SUCCESS" }), step(going)] }));
    expect(waits({ position: 1, state: "running", build_number: 10061 })).toBe(
      "Wait for #10061 to end",
    );
    expect(waits({ position: 1, state: "queued" })).toBe("Wait for step 2 to end");
    expect(removeWaitsFor(flow({ status: "running", steps: [step({ state: "running" })] }))).toBeNull();
    expect(removeWaitsFor(flow({ status: "stopped", steps: [step({ state: "SUCCESS" })] }))).toBeNull();
  });

  it("is off while the flow is going or a build is still in Jenkins", () => {
    expect(trashAction(flow({ status: "running" }))).toBe("disabled");
    expect(trashAction(flow({ status: "needs_attention" }))).toBe("disabled");
    expect(trashAction(flow({ status: "stopped", steps: [step({ state: "running" })] }))).toBe(
      "disabled",
    );
    expect(trashAction(flow({ status: "stopped", steps: [step({ state: "queued" })] }))).toBe(
      "disabled",
    );
  });
});

describe("stopChoices", () => {
  const going = (current: Partial<Step>) =>
    flow({ status: "running", current_position: 0, steps: [step(current)] });

  it("names the build on both buttons while it runs", () => {
    expect(stopChoices(going({ state: "running", build_number: 10061 }))).toEqual({
      stop: "Stop after #10061",
      abort: "Abort #10061 and stop",
    });
  });

  it("offers to cancel a build that is still queued", () => {
    expect(stopChoices(going({ state: "queued" }))).toEqual({
      stop: "Stop flow",
      abort: "Cancel queued build and stop",
    });
  });

  it("offers only the first button when there is no build yet", () => {
    expect(stopChoices(going({ state: "submit_pending" }))).toEqual({
      stop: "Stop flow",
      abort: null,
    });
    expect(stopChoices(flow({ status: "needs_attention" })).abort).toBeNull();
  });

  it("never offers a second abort", () => {
    const asked = going({ state: "running", build_number: 10061, abort_state: "requested" });

    expect(stopChoices(asked)).toEqual({ stop: "Stop after #10061", abort: null });
  });
});

describe("headerMetaOf", () => {
  it("says nothing on a draft: the cards say it", () => {
    expect(headerMetaOf(flow({ status: "draft", steps: [step({}), step({ position: 1 })] }))).toBe(
      "",
    );
  });

  it("counts nothing but the step it is on and how long it has run", () => {
    const started = "2026-09-19T10:00:00Z";
    const now = new Date("2026-09-19T10:38:12Z").getTime();
    const running = flow({
      status: "running",
      current_position: 1,
      started_at: started,
      steps: [step({}), step({ position: 1 }), step({ position: 2 })],
    });

    expect(headerMetaOf(running, now)).toBe("step 2 of 3 · 38m 12s");
  });

  it("adds what Jenkins expects is left, always as a guess", () => {
    const now = new Date("2026-09-19T10:38:12Z").getTime();
    const running = flow({
      status: "running",
      current_position: 0,
      started_at: "2026-09-19T10:00:00Z",
      estimate_ms: 50 * 60_000,
      steps: [step({}), step({ position: 1 })],
    });

    expect(headerMetaOf(running, now)).toBe("step 1 of 2 · 38m 12s · ~50m left");
    expect(headerMetaOf(flow({ status: "draft", estimate_ms: 80 * 60_000 }))).toBe("~1h 20m");
  });

  it("says a stopped flow's build still runs, and then stops counting at its last build", () => {
    const started = "2026-09-19T10:00:00Z";
    const later = new Date("2026-09-19T12:00:00Z").getTime();
    const done = step({ state: "SUCCESS", finished_at: "2026-09-19T10:20:00Z" });
    const stopped = (last: Partial<Step>) =>
      flow({ status: "stopped", started_at: started, steps: [done, step({ position: 1, ...last })] });

    expect(headerMetaOf(stopped({ state: "running", build_number: 10061 }), later)).toBe(
      "#10061 still running",
    );
    expect(headerMetaOf(stopped({ state: "queued" }), later)).toBe("step 2 still queued");
    expect(
      headerMetaOf(stopped({ state: "ABORTED", finished_at: "2026-09-19T10:31:05Z" }), later),
    ).toBe("31m 05s");
    expect(headerMetaOf(stopped({ state: "planned" }), later)).toBe("20m 00s");
  });
});

describe("what Save says", () => {
  const job = (
    preset_id: string,
    condition: Step["condition"] = "unless_failure",
    run_values: Record<string, string> = {},
  ) => ({ preset_id, condition, run_values }) as Step;
  const kept = (...steps: Step[]): SavedFlow =>
    ({
      id: "kept",
      name: "Nightly",
      steps: steps.map((item) => ({
        preset_id: item.preset_id,
        condition: item.condition,
        run_values: item.run_values,
      })),
    }) as SavedFlow;
  const build = job("build");
  const test = job("test", "always");
  const both = [build, test];

  it("is new when the flow was never kept, or the saved flow is gone", () => {
    expect(saveStateOf(flow({ saved_flow_id: null, steps: both }), null, false)).toBe("new");
    expect(saveStateOf(flow({ saved_flow_id: "kept", steps: both }), null, false)).toBe("new");
  });

  it("has nothing to save when the jobs, conditions and values match, whatever the name", () => {
    const renamed = flow({ saved_flow_id: "kept", name: "Another name", steps: both });
    expect(saveStateOf(renamed, kept(...both), false)).toBe("saved");
    // A blank value is the same as one never typed: the server keeps neither.
    const blank = flow({
      saved_flow_id: "kept",
      steps: [job("build", "unless_failure", { CLUSTER: " " }), test],
    });
    expect(saveStateOf(blank, kept(...both), false)).toBe("saved");
  });

  it("has something to save once a value is typed, changed or cleared", () => {
    const typed = job("build", "unless_failure", { CLUSTER: "example-cluster" });
    const as = (steps: Step[], saved: SavedFlow) =>
      saveStateOf(flow({ saved_flow_id: "kept", steps }), saved, false);
    expect(as([typed, test], kept(...both))).toBe("changed");
    expect(as([job("build", "unless_failure", { CLUSTER: "other" }), test], kept(typed, test))).toBe(
      "changed",
    );
    expect(as(both, kept(typed, test))).toBe("changed");
    expect(as([typed, test], kept(typed, test))).toBe("saved");
  });

  it("has something to save once a step is added, removed, moved, or its condition changes", () => {
    const saved = kept(...both);
    const as = (steps: Step[]) => saveStateOf(flow({ saved_flow_id: "kept", steps }), saved, false);
    expect(as([...both, job("deploy")])).toBe("changed");
    expect(as([build])).toBe("changed");
    expect(as([test, build])).toBe("changed");
    expect(as([build, job("test", "after_success")])).toBe("changed");
  });

  it("says saving above everything else", () => {
    expect(saveStateOf(flow({ saved_flow_id: "kept", steps: both }), kept(...both), true)).toBe("saving");
  });
});
