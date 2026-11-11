// The Run gate, checked on the rendered header.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Drift, Flow, SavedFlow, Step } from "@/api/types";
import { SAVE, SAVING } from "@/components/ui/SaveButton";
import FlowHeader, { REMOVE_DRAFT, REMOVE_RAN, UNREACHABLE } from "./FlowHeader";
import { MORE, SAVE_CHANGES } from "./FlowMenu";
import { fillLabel, fillNextTitle } from "./headerState";

const flow = (patch: Partial<Flow>): Flow =>
  ({
    id: "f",
    name: "Nightly Cypress",
    status: "draft",
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

const openMenu = () => fireEvent.click(screen.getByRole("button", { name: MORE }));
/** A menu item by the word it starts with. */
const item = (word: string) =>
  screen.getByRole("menuitem", { name: new RegExp(`^${word.replace(/[…"]/g, ".")}`) });

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
  it("offers Run on a draft with nothing missing", () => {
    let reviewed = 0;
    show({}, { onReview: () => reviewed++ });
    const run = screen.getByRole("button", { name: "Run" });
    expect(run).not.toHaveAttribute("aria-disabled");
    fireEvent.click(run);
    expect(reviewed).toBe(1);
  });

  it("says Jenkins is unreachable on a grey Run and Run again", () => {
    show({}, { canReview: false });
    expect(screen.getByRole("button", { name: "Run" })).toHaveAttribute("title", UNREACHABLE);

    cleanup();
    show({ status: "finished", result: "SUCCESS" }, { canReview: false });
    const again = screen.getByRole("button", { name: "Run again" });
    expect(again).toHaveAttribute("aria-disabled", "true");
    expect(again).toHaveAttribute("title", UNREACHABLE);
  });

  it("offers the next values to fill in place of Run, until every one is filled", () => {
    let opened = 0;
    show({}, { unfilled: 18, nextToFill: 2, onFillNext: () => opened++ });
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
    show({}, { unfilled: 1, canReview: false });
    expect(screen.getByRole("button", { name: fillLabel(1) })).toBeEnabled();
  });

  it("leads to a saved job Jenkins changed in place of Run, once every value is filled", () => {
    const drift = { added: [], removed: [], changed: [], seen_at: "" } as Drift;
    const steps = [
      step({ position: 0, preset_id: "p1", preset_name: "Cypress" }),
      step({ position: 1, preset_id: "p2", preset_name: "Deploy" }),
      step({ position: 2, preset_id: "p2", preset_name: "Deploy" }),
    ];
    const driftOf = (item: Step) => (item.preset_id === "p1" ? null : drift);

    show({ steps }, { unfilled: 1, driftOf });
    expect(screen.getByRole("button", { name: fillLabel(1) })).toBeVisible();

    cleanup();
    show({ steps }, { driftOf });
    expect(screen.queryByRole("button", { name: "Run" })).toBeNull();
    expect(screen.getByText("NOT READY")).toBeInTheDocument();
    const review = screen.getByRole("button", { name: "Review 1 job" });
    expect(review).toHaveAttribute("title", "Opens Deploy in Library");
    fireEvent.click(review);
    expect(screen.getByText("library")).toBeInTheDocument();
  });

  it("removes a flow from the board with one icon, which says what that does", () => {
    let removed = 0;
    show({}, { onDelete: () => removed++ });
    fireEvent.click(screen.getByRole("button", { name: REMOVE_DRAFT }));
    expect(removed).toBe(1);

    cleanup();
    show({ status: "finished", result: "SUCCESS" }, { onDelete: () => removed++ });
    fireEvent.click(screen.getByRole("button", { name: REMOVE_RAN }));
    expect(removed).toBe(2);
  });

  it("has no Remove while the flow cannot leave the board", () => {
    show({ status: "running", current_position: 0 });
    expect(screen.getByRole("button", { name: "Pin" })).toBeVisible();
    expect(screen.queryByRole("button", { name: REMOVE_RAN })).toBeNull();

    cleanup();
    show({ status: "stopped", steps: [step({ state: "running", build_number: 10061 })] });
    expect(screen.queryByRole("button", { name: REMOVE_RAN })).toBeNull();

    cleanup();
    show({
      status: "stopped",
      steps: [step({ state: "SUCCESS" }), step({ position: 1, state: "needs_attention" })],
    });
    expect(screen.queryByRole("button", { name: REMOVE_RAN })).toBeNull();
  });

  it("pins and unpins with one icon", () => {
    const asked: boolean[] = [];
    show({}, { onPin: (pinned) => asked.push(pinned) });
    fireEvent.click(screen.getByRole("button", { name: "Pin" }));

    cleanup();
    show({ pinned: true }, { onPin: (pinned) => asked.push(pinned) });
    fireEvent.click(screen.getByRole("button", { name: "Unpin" }));
    expect(asked).toEqual([true, false]);
  });

  it("offers Resolve beside Stop while a step needs attention", () => {
    let opened = 0;
    const steps = [step({ state: "SUCCESS" }), step({ position: 1, state: "needs_attention" })];
    show({ status: "needs_attention", steps }, { onOpenAttention: () => opened++ });
    fireEvent.click(screen.getByRole("button", { name: "Resolve step 2" }));
    expect(opened).toBe(1);
    expect(screen.getByRole("button", { name: "Stop" })).toBeVisible();
  });

  it("offers Resolve in place of Resume on a stopped flow with a step to decide", () => {
    const steps = [step({ state: "SUCCESS" }), step({ position: 1, state: "needs_attention" })];
    show({ status: "stopped", steps });
    expect(screen.getByRole("button", { name: "Resolve step 2" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Resume" })).toBeNull();

    cleanup();
    show({ status: "stopped", steps: [step({ state: "SUCCESS" })] });
    expect(screen.getByRole("button", { name: "Resume" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Resolve/ })).toBeNull();
  });

  it("keeps the focus on Stop's choices, and brings it back to Stop", () => {
    const running = [step({ state: "running", build_number: 10061 })];
    show({ status: "running", current_position: 0, steps: running });
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    const keep = screen.getByRole("button", { name: "Keep running" });
    expect(keep).toHaveFocus();
    fireEvent.click(keep);
    expect(screen.getByRole("button", { name: "Stop" })).toHaveFocus();
  });

  it("ends Stop's choices with Cancel while a step waits for a decision", () => {
    const steps = [step({ state: "needs_attention" })];
    show({ status: "needs_attention", current_position: 0, steps });
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Keep running" })).toBeNull();
  });

  it("keeps one main button, and the rest behind More actions", () => {
    show({});
    expect(screen.getByRole("button", { name: "Run" })).toHaveClass("bg-accent");
    for (const word of ["Save", "Duplicate", "Edit a copy"]) {
      expect(screen.queryByRole("button", { name: word })).toBeNull();
    }
    const more = screen.getByRole("button", { name: MORE });
    expect(more).toHaveAttribute("aria-haspopup", "menu");
    expect(more.className).not.toMatch(/\bborder\b/);
    openMenu();
    expect(screen.getAllByRole("menuitem").map((entry) => entry.textContent)).toEqual([
      SAVE,
      "Duplicate",
    ]);
    // The first item takes the focus; the arrow keys go through the rest.
    expect(item(SAVE)).toHaveFocus();
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(item("Duplicate")).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(more).toHaveFocus();
  });

  it("has no Edit or Done on a draft: a draft is always open to change", () => {
    show({});
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
    expect(screen.queryByText("EDITING")).toBeNull();
  });

  it("replaces a flow that ended with an editable copy, from its menu", () => {
    let asked = 0;
    show({ status: "finished", result: "SUCCESS" }, { onEdit: () => asked++ });

    openMenu();
    fireEvent.click(item("Edit a copy"));

    expect(asked).toBe(1);
    expect(screen.getByRole("button", { name: "Run again" })).toBeEnabled();
  });

  it("offers Save only while there is something to save", () => {
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

    let saved = 0;
    show({ saved_flow_id: "k", steps }, { keptAs: kept, onSaveAsFlow: () => saved++ });
    openMenu();
    expect(screen.getAllByRole("menuitem").map((entry) => entry.textContent)).toEqual([
      "Duplicate",
    ]);

    cleanup();
    const more = [...steps, { ...steps[0], id: "s2", position: 1 }] as Step[];
    show({ saved_flow_id: "k", steps: more }, { keptAs: kept, onSaveAsFlow: () => saved++ });
    openMenu();
    fireEvent.click(item(SAVE_CHANGES));
    expect(saved).toBe(1);
  });

  it("reads Saving… and is off while the save is on its way", () => {
    let saved = 0;
    show({ saved_flow_id: null }, { saving: true, onSaveAsFlow: () => saved++ });
    openMenu();
    const saving = item(SAVING);
    expect(saving).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(saving);
    expect(saved).toBe(0);
  });

  it("names the flow in a heading, cut short with the full name on hover", () => {
    show({ status: "finished", result: "SUCCESS" });
    const heading = screen.getByRole("heading", { level: 2, name: "Nightly Cypress" });
    expect(heading.querySelector("[title='Nightly Cypress']")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Nightly Cypress" })).toBeNull();
  });

  it("opens the name for typing when asked, and gives the focus back after Enter", () => {
    const renamed: string[] = [];
    show({}, { startRenaming: true, onRename: (name) => renamed.push(name) });
    const field = screen.getByRole("textbox", { name: "Flow name" });
    expect(field).toHaveFocus();
    expect(field).toHaveValue("Nightly Cypress");
    fireEvent.keyDown(field, { key: "Enter" });
    // Enter keeps the name as it is.
    expect(renamed).toEqual([]);
    expect(screen.getByRole("button", { name: "Nightly Cypress" })).toHaveFocus();
  });

  it("asks before removing a stopped flow, and gives the focus back to Remove when kept", () => {
    let removed = 0;
    show({ status: "stopped", steps: [step({ state: "SUCCESS" })] }, { onDelete: () => removed++ });
    fireEvent.click(screen.getByRole("button", { name: REMOVE_RAN }));
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(removed).toBe(0);
    expect(screen.getByRole("button", { name: REMOVE_RAN })).toHaveFocus();
  });
});
