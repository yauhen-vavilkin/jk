import { DndContext } from "@dnd-kit/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";

import type { Flow, Step } from "@/api/types";
import FlowSection from "./FlowSection";

it("previews numbers after an insertion without changing the underlying step", () => {
  const steps = [0, 1, 2].map((position) => ({
    id: `s${position}`, position, preset_name: `Job ${position}`, state: "planned",
    condition: "unless_failure", run_values: {}, summary: [],
  })) as unknown as Step[];
  const flow = { id: "f", name: "Draft", status: "draft", editing: true, steps } as Flow;
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
