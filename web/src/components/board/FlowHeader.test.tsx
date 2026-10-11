// The Run gate, checked on the rendered header.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Drift, Flow, SavedFlow, Step } from "@/api/types";
import { SAVE, SAVED, SAVING } from "@/components/ui/SaveButton";
import FlowHeader, {
  EDIT_ENDED,
  REMOVE_DRAFT,
  REMOVE_RAN,
  RUN_NEEDS_READY,
  STOP_FIRST,
  UNREACHABLE,
} from "./FlowHeader";
import { fillLabel, fillNextTitle } from "./headerState";

const flow = (patch: Partial<Flow>): Flow =>
  ({
    id: "f",
    name: "Nightly Cypress",
    status: "draft",
    editing: true,
    pinned: false,
    saved_flow_id: null,
    steps: [],
    current_position: null,
    started_at: null,
    finished_at: null,
    failed_at_position: null,
    estimate_ms: null,
    ...patch,
  }) as Flow;

const step = (patch: Partial<Step>): Step =>
  ({
    id: `s${patch.position ?? 0}`,
    position: 0,
    preset_id: "p1",
    preset_name: "Cypress",
    state: "planned",
    build_number: null,
    abort_state: null,
    held: false,
    run_values: {},
    ...patch,
  }) as Step;

const nothing = () => {};

type Props = ComponentProps<typeof FlowHeader>;

function show(patch: Partial<Flow>, props: Partial<Props> = {}) {
  render(
    <MemoryRouter>
      <Routes>
        <Route
          path="/"
          element={
            <FlowHeader
              flow={flow(patch)}
              busy={false}
              keptAs={null}
              saving={false}
              canReview
              onReview={nothing}
              onStop={nothing}
              onResume={nothing}
              onRename={nothing}
              onSaveAsFlow={nothing}
              onDelete={nothing}
              onOpenAttention={nothing}
              onReviewHeld={nothing}
              onRunAgain={nothing}
              onEdit={nothing}
              onDuplicate={nothing}
              onPin={nothing}
              {...props}
            />
          }
        />
        <Route path="/library/:id" element={<p>library</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("the flow header", () => {
  it("offers Run, but not while the flow is being edited, and says why on focus too", () => {
    let reviewed = 0;
    show({ editing: true }, { onReview: () => reviewed++ });
    const run = screen.getByRole("button", { name: "Run" });
    expect(run).toHaveAttribute("aria-disabled", "true");
    expect(run).toHaveAttribute("title", RUN_NEEDS_READY);
    // Still a tab stop, so the reason is reached from the keyboard.
    expect(run).not.toBeDisabled();
    fireEvent.click(run);
    expect(reviewed).toBe(0);
  });

  it("offers Run once editing is off", () => {
    let reviewed = 0;
    show({ editing: false }, { onReview: () => reviewed++ });
    const run = screen.getByRole("button", { name: "Run" });
    expect(run).not.toHaveAttribute("aria-disabled");
    fireEvent.click(run);
    expect(reviewed).toBe(1);
  });

  it("says Jenkins is unreachable on a grey Run and Run again", () => {
    show({ editing: false }, { canReview: false });
    expect(screen.getByRole("button", { name: "Run" })).toHaveAttribute("title", UNREACHABLE);

    cleanup();
    show({ status: "finished", editing: false, result: "SUCCESS" }, { canReview: false });
    const again = screen.getByRole("button", { name: "Run again" });
    expect(again).toHaveAttribute("aria-disabled", "true");
    expect(again).toHaveAttribute("title", UNREACHABLE);
  });

  it("offers the next values to fill in place of Run, until every one is filled", () => {
    let opened = 0;
    show({ editing: false }, { unfilled: 18, nextToFill: 2, onFillNext: () => opened++ });
    expect(screen.queryByRole("button", { name: "Run" })).toBeNull();
    const fill = screen.getByRole("button", { name: fillLabel(18) });
    expect(fill).toBeEnabled();
    expect(fill).toHaveAttribute("title", fillNextTitle(2));
    fireEvent.click(fill);
    expect(opened).toBe(1);
    // The count lives on the button alone.
    expect(screen.getByText("NOT READY")).toBeInTheDocument();
    expect(screen.queryByText("READY")).toBeNull();
  });

  it("leads to the values even when Jenkins cannot be reached: filling asks it nothing", () => {
    show({ editing: false }, { unfilled: 1, canReview: false });
    expect(screen.getByRole("button", { name: fillLabel(1) })).toBeEnabled();
  });

  it("keeps Run off while the flow is being edited, even with values to fill", () => {
    show({ editing: true }, { unfilled: 3 });
    const run = screen.getByRole("button", { name: "Run" });
    expect(run).toHaveAttribute("aria-disabled", "true");
    expect(run).toHaveAttribute("title", RUN_NEEDS_READY);
    expect(screen.queryByRole("button", { name: fillLabel(3) })).toBeNull();
  });

  it("leads to a saved job Jenkins changed in place of Run, once every value is filled", () => {
    const drift = { added: [], removed: [], changed: [], seen_at: "" } as Drift;
    const steps = [
      step({ position: 0, preset_id: "p1", preset_name: "Cypress" }),
      step({ position: 1, preset_id: "p2", preset_name: "Deploy" }),
      step({ position: 2, preset_id: "p2", preset_name: "Deploy" }),
    ];
    const driftOf = (item: Step) => (item.preset_id === "p1" ? null : drift);

    show({ editing: false, steps }, { unfilled: 1, driftOf });
    expect(screen.getByRole("button", { name: fillLabel(1) })).toBeVisible();

    cleanup();
    show({ editing: false, steps }, { driftOf });
    expect(screen.queryByRole("button", { name: "Run" })).toBeNull();
    expect(screen.getByText("NOT READY")).toBeInTheDocument();
    const review = screen.getByRole("button", { name: "Review 1 job" });
    expect(review).toHaveAttribute("title", "Opens Deploy in Library");
    fireEvent.click(review);
    expect(screen.getByText("library")).toBeInTheDocument();
  });

  it("removes a flow from the board, and says what that does", () => {
    show({ editing: false });
    const draft = screen.getByRole("button", { name: "Remove" });
    expect(draft).toHaveAttribute("title", REMOVE_DRAFT);
    expect(draft).not.toHaveClass("text-warn");

    cleanup();
    show({ status: "finished", editing: false, result: "SUCCESS" });
    expect(screen.getByRole("button", { name: "Remove" })).toHaveAttribute("title", REMOVE_RAN);

    cleanup();
    show({ status: "running", editing: false, current_position: 0 });
    const going = screen.getByRole("button", { name: "Remove" });
    expect(going).toBeDisabled();
    expect(going).toHaveAttribute("title", STOP_FIRST);
  });

  it("says what a stopped flow's Remove waits for", () => {
    show({ status: "stopped", editing: false, steps: [step({ state: "running", build_number: 10061 })] });
    expect(screen.getByRole("button", { name: "Remove" })).toHaveAttribute(
      "title",
      "Wait for #10061 to end",
    );

    cleanup();
    show({
      status: "stopped",
      editing: false,
      steps: [step({ state: "SUCCESS" }), step({ position: 1, state: "needs_attention" })],
    });
    const remove = screen.getByRole("button", { name: "Remove" });
    expect(remove).toBeDisabled();
    expect(remove).toHaveAttribute("title", "Resolve step 2 first");
  });

  it("offers Resolve beside Stop while a step needs attention", () => {
    let opened = 0;
    const steps = [step({ state: "SUCCESS" }), step({ position: 1, state: "needs_attention" })];
    show({ status: "needs_attention", editing: false, steps }, { onOpenAttention: () => opened++ });
    fireEvent.click(screen.getByRole("button", { name: "Resolve step 2" }));
    expect(opened).toBe(1);
    expect(screen.getByRole("button", { name: "Stop" })).toBeVisible();
  });

  it("offers Resolve in place of Resume on a stopped flow with a step to decide", () => {
    const steps = [step({ state: "SUCCESS" }), step({ position: 1, state: "needs_attention" })];
    show({ status: "stopped", editing: false, steps });
    expect(screen.getByRole("button", { name: "Resolve step 2" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Resume" })).toBeNull();

    cleanup();
    show({ status: "stopped", editing: false, steps: [step({ state: "SUCCESS" })] });
    expect(screen.getByRole("button", { name: "Resume" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Resolve/ })).toBeNull();
  });

  it("keeps the focus on Stop's choices, and brings it back to Stop", () => {
    const running = [step({ state: "running", build_number: 10061 })];
    show({ status: "running", editing: false, current_position: 0, steps: running });
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    const keep = screen.getByRole("button", { name: "Keep running" });
    expect(keep).toHaveFocus();
    fireEvent.click(keep);
    expect(screen.getByRole("button", { name: "Stop" })).toHaveFocus();
  });

  it("ends Stop's choices with Cancel while a step waits for a decision", () => {
    const steps = [step({ state: "needs_attention" })];
    show({ status: "needs_attention", editing: false, current_position: 0, steps });
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Keep running" })).toBeNull();
  });

  it("says in words what each icon button does, without a frame or a title that repeats it", () => {
    show({ editing: false });
    for (const word of ["Edit", "Pin", "Save", "Duplicate", "Remove"]) {
      const button = screen.getByRole("button", { name: word });
      expect(button).toBeVisible();
      expect(button.className).not.toMatch(/\bborder\b/);
    }
    for (const word of ["Edit", "Pin", "Save", "Duplicate"]) {
      expect(screen.getByRole("button", { name: word })).not.toHaveAttribute("title");
    }
    // Only the main button keeps its frame.
    expect(screen.getByRole("button", { name: "Run" })).toHaveClass("bg-accent");
  });

  it("calls the pencil Done while the flow is being edited", () => {
    const asked: boolean[] = [];
    show({ editing: true }, { onEdit: (editing) => asked.push(editing) });
    const done = screen.getByRole("button", { name: "Done" });
    expect(done).toHaveClass("text-text");
    expect(done).not.toHaveClass("text-accent");
    fireEvent.click(done);
    expect(asked).toEqual([false]);
    expect(screen.getByText("EDITING")).toHaveClass("text-text");

    cleanup();
    show({ editing: false });
    const edit = screen.getByRole("button", { name: "Edit" });
    expect(edit).toHaveClass("text-key");
    expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
  });

  it("replaces a flow that ended with an editable copy, and says so", () => {
    const asked: boolean[] = [];
    show(
      { status: "finished", editing: false, result: "SUCCESS" },
      { onEdit: (editing) => asked.push(editing) },
    );

    const pencil = screen.getByRole("button", { name: "Edit" });
    expect(pencil).toHaveAttribute("title", EDIT_ENDED);
    fireEvent.click(pencil);

    expect(asked).toEqual([true]);
    expect(screen.getByRole("button", { name: "Run again" })).toBeEnabled();
  });

  it("lights Save only while there is something to save, and reads Saved when there is not", () => {
    const steps = [
      { id: "s1", position: 0, preset_id: "p1", condition: "unless_failure", run_values: {} },
    ] as unknown as Step[];
    const kept = {
      id: "k",
      name: "Nightly kept",
      steps: [
        {
          preset_id: "p1",
          condition: "unless_failure",
          run_values: {},
        },
      ],
    } as SavedFlow;

    show({ saved_flow_id: "k", steps }, { keptAs: kept });
    const saved = screen.getByRole("button", { name: SAVED });
    expect(saved).toHaveAttribute("aria-disabled", "true");
    expect(saved).toHaveClass("text-dim");
    expect(saved).toHaveAttribute("title", 'Saved as "Nightly kept"');
    expect(saved.querySelector("svg.lucide-check")).not.toBeNull();

    cleanup();
    const more = [...steps, { ...steps[0], id: "s2", position: 1 }] as Step[];
    show({ saved_flow_id: "k", steps: more }, { keptAs: kept });
    const changed = screen.getByRole("button", { name: SAVE });
    expect(changed).toBeEnabled();
    expect(changed).toHaveClass("text-text");

    cleanup();
    show({ saved_flow_id: null, steps });
    const fresh = screen.getByRole("button", { name: SAVE });
    expect(fresh).toBeEnabled();
    expect(fresh).toHaveClass("text-key");
  });

  it("reads Saving… and is off while the save is on its way, keeping the focus", () => {
    let saved = 0;
    show({ saved_flow_id: null }, { saving: true, onSaveAsFlow: () => saved++ });
    const saving = screen.getByRole("button", { name: SAVING });
    expect(saving).toHaveAttribute("aria-disabled", "true");
    expect(saving).not.toBeDisabled();
    fireEvent.click(saving);
    expect(saved).toBe(0);
  });

  it("names the flow in a heading, cut short with the full name on hover", () => {
    show({ editing: false });
    const heading = screen.getByRole("heading", { level: 2, name: "Nightly Cypress" });
    expect(heading.querySelector("[title='Nightly Cypress']")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Nightly Cypress" })).toBeNull();
  });

  it("opens the name for typing when asked, and gives the focus back after Enter", () => {
    const renamed: string[] = [];
    show({ editing: true }, { startRenaming: true, onRename: (name) => renamed.push(name) });
    const field = screen.getByRole("textbox", { name: "Flow name" });
    expect(field).toHaveFocus();
    expect(field).toHaveValue("Nightly Cypress");
    fireEvent.keyDown(field, { key: "Enter" });
    // Enter keeps the name as it is.
    expect(renamed).toEqual([]);
    expect(screen.getByRole("button", { name: "Nightly Cypress" })).toHaveFocus();
  });

  it("gives the focus back to Remove when its question is kept", () => {
    show({ status: "stopped", editing: false, steps: [step({ state: "SUCCESS" })] });
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(screen.getByRole("button", { name: "Remove" })).toHaveFocus();
  });
});
