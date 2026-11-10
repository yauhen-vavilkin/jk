import { DndContext } from "@dnd-kit/core";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";

import type { Flow, Step } from "@/api/types";
import FlowSection from "./FlowSection";

it("previews numbers after an insertion without changing the underlying step", () => {
  const steps = [0, 1, 2].map((position) => ({
    id: `s${position}`, position, preset_name: `Job ${position}`, state: "planned",
    condition: "unless_failure", run_values: {}, summary: [],
  })) as unknown as Step[];
  const flow = { id: "f", name: "Draft", status: "draft", steps } as Flow;
  const onCondition = vi.fn();
  const nothing = () => {};
  const show = (insertIndex: number | null) => (
    <MemoryRouter><DndContext><FlowSection
      flow={flow} canReview onReview={nothing} onStop={nothing} onResume={nothing}
      onRename={nothing} onSaveAsFlow={nothing} onDelete={nothing} onOpenAttention={nothing}
      onCondition={onCondition} onRemoveStep={nothing} onFillValues={nothing} askedOf={() => []}
      onReviewHeld={nothing} onRunAgain={nothing} onEdit={nothing} onDuplicate={nothing}
      onPin={nothing} busy={false} keptAs={null} saving={false} insertIndex={insertIndex}
    /></DndContext></MemoryRouter>
  );
  const { rerender } = render(show(1));
  expect(screen.getByRole("button", { name: "Step 1, Job 0" })).toHaveTextContent("STEP 1");
  expect(screen.getByRole("button", { name: "Step 3, Job 1" })).toHaveTextContent("STEP 3");
  expect(screen.getByRole("button", { name: "Step 4, Job 2" })).toHaveTextContent("STEP 4");
  fireEvent.click(screen.getByRole("button", { name: "Step 3, Job 1" }));
  expect(screen.getByRole("dialog", { name: "Step 2 details" })).toBeInTheDocument();
  expect(steps.map((step) => step.position)).toEqual([0, 1, 2]);
  rerender(show(null));
  expect(screen.getByRole("button", { name: "Step 2, Job 1" })).toHaveTextContent("STEP 2");
});

const planned = (position: number, state = "planned") =>
  ({
    id: `f:${position}`, position, preset_id: `p${position}`, preset_name: `Job ${position}`,
    state, condition: "unless_failure", run_values: {},
    summary: [], held: false, build_number: null, abort_state: null,
  }) as unknown as Step;

function sectionOf(status: Flow["status"], onRemoveStep: (step: Step) => void, second = planned(1)) {
  const first = planned(0, status === "draft" ? "planned" : "running");
  const flow = { id: "f", name: "Flow", status, steps: [first, second] } as Flow;
  const nothing = () => {};
  return (
    <MemoryRouter><DndContext><FlowSection
      flow={flow} canReview onReview={nothing} onStop={nothing} onResume={nothing}
      onRename={nothing} onSaveAsFlow={nothing} onDelete={nothing} onOpenAttention={nothing}
      onCondition={nothing} onRemoveStep={onRemoveStep} onFillValues={nothing} askedOf={() => []}
      onReviewHeld={nothing} onRunAgain={nothing} onEdit={nothing} onDuplicate={nothing}
      onPin={nothing} busy={false} keptAs={null} saving={false} insertIndex={null}
    /></DndContext></MemoryRouter>
  );
}

it("asks on the card before a step of a running flow is removed", () => {
  const removed: string[] = [];
  render(sectionOf("running", (step) => removed.push(step.id)));

  fireEvent.click(screen.getByRole("button", { name: "Remove step" }));
  expect(screen.getByText("Remove step 2?")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Keep" })).toHaveFocus();
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Keep" }));
  expect(removed).toEqual([]);
  expect(screen.queryByText("Remove step 2?")).toBeNull();
  expect(screen.getByRole("button", { name: "Remove step" })).toHaveFocus();

  fireEvent.click(screen.getByRole("button", { name: "Remove step" }));
  const question = screen.getByText("Remove step 2?").parentElement as HTMLElement;
  fireEvent.click(within(question).getByRole("button", { name: "Remove" }));
  expect(removed).toEqual(["f:1"]);
});

it("removes a step of a draft at once, without a question", () => {
  const removed: string[] = [];
  render(sectionOf("draft", (step) => removed.push(step.id)));

  fireEvent.click(screen.getAllByRole("button", { name: "Remove step" })[1] as HTMLElement);

  expect(removed).toEqual(["f:1"]);
  expect(screen.queryByText(/Remove step \d\?/)).toBeNull();
});

it("drops the question when another job takes the card's place", () => {
  const { rerender } = render(sectionOf("running", () => {}));
  fireEvent.click(screen.getByRole("button", { name: "Remove step" }));
  expect(screen.getByText("Remove step 2?")).toBeInTheDocument();

  const other = { ...planned(1), preset_id: "p9", preset_name: "Job 9" } as Step;
  rerender(sectionOf("running", () => {}, other));

  expect(screen.queryByText("Remove step 2?")).toBeNull();
});
