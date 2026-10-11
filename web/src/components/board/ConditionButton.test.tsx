import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Flow, Step } from "@/api/types";
import { CONDITION_LABELS } from "@/lib/conditions";
import ConditionButton from "./ConditionButton";
import { StepCardBody } from "./StepCard";

function show() {
  render(<ConditionButton condition="unless_failure" editable onChange={() => {}} />);
  return screen.getByRole("button", { name: CONDITION_LABELS.unless_failure });
}

const menus = () => screen.queryAllByRole("menu").length;

describe("the condition button", () => {
  it("closes its menu on a second press, from a screen reader as from a mouse", () => {
    const button = show();
    fireEvent.click(button);
    expect(menus()).toBe(1);

    // A screen reader presses with a mousedown and a click that carries no count.
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);
    fireEvent.click(button, { detail: 0 });
    expect(menus()).toBe(0);

    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);
    fireEvent.click(button, { detail: 1 });
    expect(menus()).toBe(1);
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);
    fireEvent.click(button, { detail: 1 });
    expect(menus()).toBe(0);
  });

  it("draws no box, so a check does not read as a ticked checkbox", () => {
    expect(show().className).not.toMatch(/(^|\s)border(\s|$|-)/);
  });

  it("closes on a press anywhere else, and a press released off it swallows no key", () => {
    const button = show();
    fireEvent.click(button);
    fireEvent.mouseDown(document.body);
    expect(menus()).toBe(0);

    fireEvent.click(button);
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(document.body);
    expect(menus()).toBe(1);
    // Enter on the button: a click with no mousedown before it.
    fireEvent.click(button, { detail: 0 });
    expect(menus()).toBe(0);
    fireEvent.click(button, { detail: 0 });
    expect(menus()).toBe(1);
  });
});

describe("the condition of a step in a started flow", () => {
  it("changes only on a step that waits for its review, as the server allows", () => {
    const flow = { id: "f", status: "running", editing: false } as Flow;
    const card = (held: boolean) => {
      const step = { id: "s1", position: 1, condition: "unless_failure", state: "planned", held, run_values: {}, summary: [] };
      return <StepCardBody step={step as unknown as Step} flow={flow} onCondition={() => {}} />;
    };
    const { rerender } = render(card(false));
    expect(screen.getByRole("button", { name: CONDITION_LABELS.unless_failure })).toBeDisabled();
    rerender(card(true));
    expect(screen.getByRole("button", { name: CONDITION_LABELS.unless_failure })).toBeEnabled();
  });
});
